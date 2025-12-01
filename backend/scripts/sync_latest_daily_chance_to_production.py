"""
同步最新的每日机会数据到生产主库
包括：赔率总分、支撑线、压力线、成交量类型

主库地址：sh-cdb-2hxu41ka.sql.tencentcdb.com:21648（可写）
"""
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 添加项目根目录到路径（config.py所在位置）
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

import json
from datetime import datetime
from typing import List, Dict
import pymysql

# 使用独立的数据库连接（生产主库）
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
from infrastructure.logging.logger import get_logger
from domain.services.volume_type_service import VolumeTypeService

logger = get_logger(__name__)


def load_stock_config() -> List[Dict]:
    """加载股票配置"""
    config_path = os.path.join(os.path.dirname(__file__), '../infrastructure/config/stock_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    stocks = []
    for nature, stock_list in config.items():
        for stock in stock_list:
            stocks.append({
                'code': stock['code'],
                'name': stock['name'],
                'table': stock['table'],
                'nature': nature
            })
    
    return stocks


def get_predicted_volume(table_name: str) -> float:
    """获取预测成交量"""
    try:
        from application.services.kline_service import KLineApplicationService
        from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
        
        kline_repo = KLineRepositoryImpl()
        kline_service = KLineApplicationService(kline_repo)
        
        result = kline_service.predict_today_volume(table_name)
        
        if result.get('predicted_volume'):
            return result['predicted_volume']
        else:
            logger.warning(f"无法预测成交量: {table_name}, {result.get('message')}")
            return None
            
    except Exception as e:
        logger.error(f"获取预测成交量失败: {table_name}, {e}")
        return None


def calculate_volume_type(table_name: str, predicted_volume: float) -> str:
    """计算成交量类型"""
    try:
        if not predicted_volume:
            return None
        
        volume_type = VolumeTypeService.calculate_volume_type_with_predicted(
            table_name, predicted_volume
        )
        
        return volume_type
        
    except Exception as e:
        logger.error(f"计算成交量类型失败: {table_name}, {e}")
        return None


def save_to_database(stock_code: str, stock_name: str, stock_nature: str, 
                     api_data: List[Dict], volume_type_map: Dict[str, str]) -> int:
    """
    保存到数据库（只保存最近7天的数据）
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        stock_nature: 股性
        api_data: API返回的数据
        volume_type_map: 日期到成交量类型的映射
        
    Returns:
        保存的记录数
    """
    if not api_data:
        return 0
    
    try:
        # 计算7天前的日期
        from datetime import datetime, timedelta
        seven_days_ago = datetime.now() - timedelta(days=7)
        seven_days_ago_str = seven_days_ago.strftime('%Y-%m-%d')
        
        # 使用生产主库连接
        conn = pymysql.connect(**MASTER_DB_CONFIG)
        try:
            cursor = conn.cursor()
            
            sql = """
                INSERT INTO b_daily_chance (
                    stock_code, stock_name, stock_nature, date, chance,
                    day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
                    support_price, pressure_price, volume_type
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON DUPLICATE KEY UPDATE
                    stock_name = VALUES(stock_name),
                    stock_nature = VALUES(stock_nature),
                    chance = VALUES(chance),
                    day_win_ratio_score = VALUES(day_win_ratio_score),
                    week_win_ratio_score = VALUES(week_win_ratio_score),
                    total_win_ratio_score = VALUES(total_win_ratio_score),
                    support_price = VALUES(support_price),
                    pressure_price = VALUES(pressure_price),
                    volume_type = VALUES(volume_type)
            """
            
            saved_count = 0
            skipped_count = 0
            
            for item in api_data:
                try:
                    # 解析日期
                    date_str = item.get('day', '')
                    if not date_str:
                        continue
                    
                    date_only = date_str.split()[0]  # "2024-06-07 00:00:00" -> "2024-06-07"
                    
                    # 只保存最近7天的数据
                    if date_only < seven_days_ago_str:
                        skipped_count += 1
                        continue
                    
                    # 解析赔率描述
                    win_ratio_desc = item.get('winRatioDescription', '')
                    day_score, week_score, total_score = parse_win_ratio_description(win_ratio_desc)
                    
                    # 获取成交量类型
                    volume_type = volume_type_map.get(date_only)
                    
                    # 支撑线和压力线
                    # API返回的已经是整数格式（如1600，表示16.00元），直接保存即可
                    support_price = item.get('supportPrice')
                    pressure_price = item.get('pressurePrice')
                    
                    support_price_int = int(float(support_price)) if support_price else None
                    pressure_price_int = int(float(pressure_price)) if pressure_price else None
                    
                    cursor.execute(sql, (
                        stock_code,
                        stock_name,
                        stock_nature,
                        date_only,
                        float(item.get('chance', 0)),
                        day_score,
                        week_score,
                        total_score,
                        support_price_int,
                        pressure_price_int,
                        volume_type
                    ))
                    
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"保存单条记录失败: {stock_code} {date_str}, {e}")
                    continue
            
            conn.commit()
            if skipped_count > 0:
                logger.info(f"    跳过 {skipped_count} 条历史数据（超过7天）")
            return saved_count
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"保存数据库失败: {stock_code}, {e}", exc_info=True)
        return 0


def parse_win_ratio_description(description: str) -> tuple:
    """
    解析赔率描述
    
    Args:
        description: 例如 "日：18.7 周：18.96 总：37.66"
        
    Returns:
        (day_score, week_score, total_score)
    """
    import re
    
    day_score = 0.0
    week_score = 0.0
    total_score = 0.0
    
    try:
        # 匹配 "日：18.7"
        day_match = re.search(r'日[：:]\s*([\d.]+)', description)
        if day_match:
            day_score = float(day_match.group(1))
        
        # 匹配 "周：18.96"
        week_match = re.search(r'周[：:]\s*([\d.]+)', description)
        if week_match:
            week_score = float(week_match.group(1))
        
        # 匹配 "总：37.66"
        total_match = re.search(r'总[：:]\s*([\d.]+)', description)
        if total_match:
            total_score = float(total_match.group(1))
    
    except Exception as e:
        logger.warning(f"解析赔率描述失败: {description}, {e}")
    
    return day_score, week_score, total_score


def sync_stock(stock: Dict, api_client: DailyChanceApiClient) -> Dict:
    """
    同步单个股票
    
    Returns:
        包含统计信息的字典
    """
    stock_code = stock['code']
    stock_name = stock['name']
    stock_table = stock['table']
    stock_nature = stock['nature']
    
    result = {
        'code': stock_code,
        'name': stock_name,
        'success': False,
        'records': 0,
        'volume_type': None,
        'error': None
    }
    
    try:
        logger.info(f"{'='*60}")
        logger.info(f"开始同步: {stock_name} ({stock_code})")
        
        # 1. 调用API获取每日机会数据
        logger.info(f"  [1/3] 调用API获取数据...")
        api_data = api_client.get_daily_chance(stock_code)
        
        if not api_data:
            result['error'] = '未获取到API数据'
            logger.warning(f"  ❌ {stock_name} 未获取到数据")
            return result
        
        logger.info(f"  ✅ 获取到 {len(api_data)} 条记录")
        
        # 2. 计算最新一天的成交量类型
        logger.info(f"  [2/3] 计算成交量类型...")
        volume_type_map = {}
        
        # 获取预测成交量
        predicted_volume = get_predicted_volume(stock_table)
        
        if predicted_volume:
            # 计算成交量类型
            volume_type = calculate_volume_type(stock_table, predicted_volume)
            
            if volume_type:
                # 找到最新一天的日期
                latest_date = None
                for item in api_data:
                    date_str = item.get('day', '')
                    if date_str:
                        date_only = date_str.split()[0]
                        if not latest_date or date_only > latest_date:
                            latest_date = date_only
                
                if latest_date:
                    volume_type_map[latest_date] = volume_type
                    result['volume_type'] = volume_type
                    logger.info(f"  ✅ 最新日期 {latest_date} 成交量类型: {volume_type}")
            else:
                logger.info(f"  ℹ️  未匹配任何成交量类型")
        else:
            logger.warning(f"  ⚠️  无法获取预测成交量")
        
        # 3. 保存到数据库
        logger.info(f"  [3/3] 保存到数据库...")
        saved_count = save_to_database(
            stock_code, stock_name, stock_nature, 
            api_data, volume_type_map
        )
        
        result['records'] = saved_count
        result['success'] = True
        logger.info(f"  ✅ {stock_name} 同步完成，保存 {saved_count} 条记录")
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"  ❌ {stock_name} 同步失败: {e}", exc_info=True)
    
    return result


def main():
    """主函数"""
    print("=" * 80)
    print("同步最新每日机会数据到生产数据库")
    print("=" * 80)
    print()
    
    # 加载股票配置
    logger.info("加载股票配置...")
    stocks = load_stock_config()
    logger.info(f"共加载 {len(stocks)} 支股票")
    
    # 按股性分组统计
    nature_count = {}
    for stock in stocks:
        nature = stock['nature']
        nature_count[nature] = nature_count.get(nature, 0) + 1
    
    for nature, count in nature_count.items():
        logger.info(f"  - {nature}: {count} 支")
    
    print()
    
    # 创建API客户端
    api_client = DailyChanceApiClient()
    
    # 统计信息
    success_count = 0
    failed_count = 0
    total_records = 0
    failed_stocks = []
    
    # 同步每支股票
    for i, stock in enumerate(stocks, 1):
        print(f"\n进度: {i}/{len(stocks)}")
        
        result = sync_stock(stock, api_client)
        
        if result['success']:
            success_count += 1
            total_records += result['records']
        else:
            failed_count += 1
            failed_stocks.append({
                'code': result['code'],
                'name': result['name'],
                'error': result['error']
            })
    
    # 打印总结
    print()
    print("=" * 80)
    print("同步完成")
    print("=" * 80)
    logger.info(f"总股票数: {len(stocks)}")
    logger.info(f"成功: {success_count}")
    logger.info(f"失败: {failed_count}")
    logger.info(f"总记录数: {total_records}")
    
    if failed_stocks:
        print()
        logger.warning("失败的股票:")
        for stock in failed_stocks:
            logger.warning(f"  - {stock['name']} ({stock['code']}): {stock['error']}")
    
    print()
    logger.info("脚本执行完成")


if __name__ == "__main__":
    main()

