"""
定时任务：每天晚上5点更新生产数据库的每日机会数据
包括：赔率总分、支撑线、压力线、成交量类型
"""
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 添加项目根目录到路径
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

import json
import pymysql
import requests
from datetime import datetime, timedelta
from typing import List, Dict
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'logs', 'daily_chance_scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 生产主库配置
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 外部API配置
API_BASE_URL = "http://121.5.174.81:8005"


def load_stock_config() -> List[Dict]:
    """加载股票配置（59支股票）"""
    config_path = os.path.join(backend_dir, 'infrastructure/config/stock_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    stocks = []
    for nature, stock_list in config.items():
        for stock in stock_list:
            stocks.append({
                'code': stock['code'],
                'name': stock['name'],
                'table_name': f"basic_data_{stock['code'].lower()}"
            })
    
    return stocks


def parse_win_ratio_description(description: str) -> tuple:
    """
    解析赔率描述，提取日线赔率得分、周线赔率得分、赔率总分
    
    格式：【此为波段赔率算法】日线赔率得分：29.23，周线赔率得分：6.26，赔率总分：35.49
    """
    import re
    
    day_score = 0.0
    week_score = 0.0
    total_score = 0.0
    
    try:
        # 提取日线赔率得分
        day_match = re.search(r'日线赔率得分[：:]\s*([\d.]+)', description)
        if day_match:
            day_score = float(day_match.group(1))
        
        # 提取周线赔率得分
        week_match = re.search(r'周线赔率得分[：:]\s*([\d.]+)', description)
        if week_match:
            week_score = float(week_match.group(1))
        
        # 提取赔率总分
        total_match = re.search(r'赔率总分[：:]\s*([\d.]+)', description)
        if total_match:
            total_score = float(total_match.group(1))
            
    except Exception as e:
        logger.warning(f"解析赔率描述失败: {description}, {e}")
    
    return day_score, week_score, total_score


def fetch_daily_chance_from_api(stock_code: str) -> List[Dict]:
    """从外部API获取每日机会数据"""
    try:
        url = f"{API_BASE_URL}/stock/getDailyChanceWithBeauty"
        params = {'code': stock_code}
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('code') != 200:
            logger.error(f"API返回错误: {stock_code}, {data.get('msg')}")
            return []
        
        return data.get('data', [])
        
    except Exception as e:
        logger.error(f"获取API数据失败: {stock_code}, {e}")
        return []


def calculate_volume_type(table_name: str, predicted_volume: float) -> str:
    """计算成交量类型"""
    try:
        from domain.services.volume_type_service import VolumeTypeService
        volume_type = VolumeTypeService.calculate_volume_type_with_predicted(table_name, predicted_volume)
        return volume_type if volume_type else ''
    except Exception as e:
        logger.error(f"计算成交量类型失败: {table_name}, {e}")
        return ''


def save_to_database(stock_code: str, table_name: str, api_data: List[Dict]) -> int:
    """
    保存数据到生产数据库
    只保存最新1天的数据
    """
    if not api_data:
        return 0
    
    connection = None
    saved_count = 0
    
    try:
        # 连接生产主库
        connection = pymysql.connect(**MASTER_DB_CONFIG)
        cursor = connection.cursor()
        
        # 获取最新的一条数据
        latest_record = api_data[0]
        
        # 提取数据
        date_str = latest_record.get('date', '')
        if not date_str:
            logger.warning(f"日期为空，跳过: {stock_code}")
            return 0
        
        # 检查是否是今天的数据
        today = datetime.now().strftime('%Y-%m-%d')
        if date_str != today:
            logger.info(f"不是今天的数据，跳过: {stock_code}, 数据日期={date_str}, 今天={today}")
            return 0
        
        volume = latest_record.get('volume', 0)
        support_price = latest_record.get('supportPrice')
        pressure_price = latest_record.get('pressurePrice')
        win_ratio_description = latest_record.get('winRatioDescription', '')
        
        # 解析赔率分数
        day_win_ratio_score, week_win_ratio_score, total_win_ratio_score = parse_win_ratio_description(win_ratio_description)
        
        # 计算成交量类型
        volume_type = calculate_volume_type(table_name, volume) if volume else ''
        
        # 转换价格（API返回的是整数，如1600表示16.00）
        support_price_int = int(float(support_price)) if support_price else None
        pressure_price_int = int(float(pressure_price)) if pressure_price else None
        
        # 执行UPSERT（如果存在则更新，不存在则插入）
        upsert_sql = """
        INSERT INTO b_daily_chance 
        (stock_code, date, day_win_ratio_score, week_win_ratio_score, total_win_ratio_score, 
         support_price, pressure_price, volume_type, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            day_win_ratio_score = VALUES(day_win_ratio_score),
            week_win_ratio_score = VALUES(week_win_ratio_score),
            total_win_ratio_score = VALUES(total_win_ratio_score),
            support_price = VALUES(support_price),
            pressure_price = VALUES(pressure_price),
            volume_type = VALUES(volume_type),
            updated_at = NOW()
        """
        
        cursor.execute(upsert_sql, (
            stock_code,
            date_str,
            day_win_ratio_score,
            week_win_ratio_score,
            total_win_ratio_score,
            support_price_int,
            pressure_price_int,
            volume_type
        ))
        
        connection.commit()
        saved_count = 1
        
        logger.info(f"✅ {stock_code} {date_str} - 赔率总分:{total_win_ratio_score:.2f}, 成交量类型:{volume_type or '无'}")
        
    except Exception as e:
        logger.error(f"保存数据库失败: {stock_code}, {e}", exc_info=True)
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection.close()
    
    return saved_count


def sync_daily_chance_job():
    """定时任务：同步每日机会数据"""
    logger.info("=" * 80)
    logger.info("🚀 开始定时同步任务：更新每日机会数据")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # 加载股票列表
    stocks = load_stock_config()
    logger.info(f"共需处理 {len(stocks)} 支股票")
    
    success_count = 0
    failed_stocks = []
    
    # 逐个处理股票
    for i, stock in enumerate(stocks, 1):
        stock_code = stock['code']
        table_name = stock['table_name']
        
        try:
            logger.info(f"[{i}/{len(stocks)}] 处理 {stock_code} ({stock['name']})...")
            
            # 从API获取数据
            api_data = fetch_daily_chance_from_api(stock_code)
            
            if not api_data:
                logger.warning(f"  ⚠️  未获取到数据")
                failed_stocks.append(stock_code)
                continue
            
            # 保存到数据库（只保存最新1天）
            saved = save_to_database(stock_code, table_name, api_data)
            
            if saved > 0:
                success_count += 1
            else:
                failed_stocks.append(stock_code)
                
        except Exception as e:
            logger.error(f"  ❌ 处理失败: {e}")
            failed_stocks.append(stock_code)
    
    # 输出汇总
    logger.info("=" * 80)
    logger.info(f"✅ 定时任务完成")
    logger.info(f"成功: {success_count}/{len(stocks)}")
    if failed_stocks:
        logger.warning(f"失败的股票 ({len(failed_stocks)}): {', '.join(failed_stocks)}")
    logger.info("=" * 80)


def main():
    """主函数：启动定时任务调度器"""
    logger.info("🌟 每日机会数据定时同步服务启动")
    logger.info(f"调度时间: 每天 17:00")
    logger.info(f"生产主库: {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
    logger.info("-" * 80)
    
    # 创建日志目录
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 创建调度器
    scheduler = BlockingScheduler()
    
    # 添加定时任务：每天17:00执行
    scheduler.add_job(
        sync_daily_chance_job,
        trigger=CronTrigger(hour=17, minute=0),
        id='daily_chance_sync',
        name='同步每日机会数据到生产库',
        replace_existing=True
    )
    
    # 可选：立即执行一次测试
    # logger.info("🔧 立即执行一次测试...")
    # sync_daily_chance_job()
    
    try:
        logger.info("✅ 调度器已启动，等待执行任务...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("⛔ 调度器已停止")


if __name__ == '__main__':
    main()

