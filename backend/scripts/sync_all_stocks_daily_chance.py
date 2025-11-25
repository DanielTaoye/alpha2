"""
从 all_stock 表获取所有股票，调用接口获取每日机会数据并存入 b_daily_chance 表
"""
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import time

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from infrastructure.persistence.database import DatabaseConnection
from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
from domain.models.daily_chance import DailyChance
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def get_all_active_stocks(limit: int = None) -> List[Dict]:
    """
    从 all_stock 表获取所有未退市的股票
    
    Args:
        limit: 限制获取的股票数量，用于测试
        
    Returns:
        股票列表 [{'code': 'SH600000', 'name': '浦发银行', 'nature': '波段'}, ...]
    """
    try:
        with DatabaseConnection.get_connection_context() as conn:
            import pymysql.cursors
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 查询未退市的股票（是否退市 != 1），获取股性（nature）
            sql = """
                SELECT code, name, nature 
                FROM all_stock 
                WHERE `是否退市` != 1 OR `是否退市` IS NULL
                ORDER BY code
            """
            
            if limit:
                sql += f" LIMIT {limit}"
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            stocks = []
            for row in results:
                stocks.append({
                    'code': row['code'],
                    'name': row['name'],
                    'nature': row['nature'] or '未分类'  # 如果nature为空，设置默认值
                })
            
            return stocks
            
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}", exc_info=True)
        return []


def save_daily_chance_data(stock_code: str, stock_name: str, stock_nature: str, api_data: List[Dict]) -> int:
    """
    保存每日机会数据到 b_daily_chance 表
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        stock_nature: 股性
        api_data: API返回的数据
        
    Returns:
        保存的记录数
    """
    if not api_data:
        return 0
    
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            
            # 准备批量插入SQL
            sql = """
                INSERT INTO b_daily_chance (
                    stock_code, stock_name, stock_nature, date, chance,
                    day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
                    support_price, pressure_price
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON DUPLICATE KEY UPDATE
                    stock_name = VALUES(stock_name),
                    stock_nature = VALUES(stock_nature),
                    chance = VALUES(chance),
                    day_win_ratio_score = VALUES(day_win_ratio_score),
                    week_win_ratio_score = VALUES(week_win_ratio_score),
                    total_win_ratio_score = VALUES(total_win_ratio_score),
                    support_price = VALUES(support_price),
                    pressure_price = VALUES(pressure_price)
            """
            
            saved_count = 0
            
            for item in api_data:
                try:
                    # 解析日期
                    date_str = item.get('day', '')
                    if not date_str:
                        continue
                    
                    # 处理日期格式 "2024-06-07 00:00:00" -> "2024-06-07"
                    date_obj = datetime.strptime(date_str.split()[0], '%Y-%m-%d')
                    
                    # 解析赔率描述
                    win_ratio_desc = item.get('winRatioDescription', '')
                    day_score, week_score, total_score = parse_win_ratio_description(win_ratio_desc)
                    
                    # 准备数据
                    values = (
                        stock_code,
                        stock_name,
                        stock_nature,  # 从 all_stock 表获取的股性
                        date_obj,
                        float(item.get('chance', 0)),
                        day_score,
                        week_score,
                        total_score,
                        float(item.get('supportPrice')) if item.get('supportPrice') else None,
                        float(item.get('pressurePrice')) if item.get('pressurePrice') else None
                    )
                    
                    cursor.execute(sql, values)
                    saved_count += 1
                    
                except Exception as e:
                    logger.warning(f"解析数据失败 {stock_code} {date_str}: {e}")
                    continue
            
            conn.commit()
            return saved_count
            
    except Exception as e:
        logger.error(f"保存数据失败 {stock_code}: {e}", exc_info=True)
        return 0


def parse_win_ratio_description(description: str) -> tuple:
    """
    解析赔率描述字符串
    
    Args:
        description: 赔率描述，如 "【此为波段赔率算法】日线赔率得分：13.83，周线赔率得分：0.00，赔率总分：13.83"
        
    Returns:
        (日线得分, 周线得分, 总分)
    """
    import re
    
    day_score = 0.0
    week_score = 0.0
    total_score = 0.0
    
    try:
        # 匹配 "日线赔率得分：X.XX"
        day_match = re.search(r'日线赔率得分[：:]\s*([\d.]+)', description)
        if day_match:
            day_score = float(day_match.group(1))
        
        # 匹配 "周线赔率得分：X.XX"
        week_match = re.search(r'周线赔率得分[：:]\s*([\d.]+)', description)
        if week_match:
            week_score = float(week_match.group(1))
        
        # 匹配 "赔率总分：X.XX"
        total_match = re.search(r'赔率总分[：:]\s*([\d.]+)', description)
        if total_match:
            total_score = float(total_match.group(1))
            
    except Exception as e:
        logger.warning(f"解析赔率描述失败: {description}, 错误: {e}")
    
    return day_score, week_score, total_score


def sync_single_stock(stock_code: str, stock_name: str, stock_nature: str, api_client: DailyChanceApiClient) -> Dict:
    """
    同步单个股票的数据
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        stock_nature: 股性
        api_client: API客户端
        
    Returns:
        结果字典
    """
    logger.info(f"开始处理: {stock_code} ({stock_name}) - 股性: {stock_nature}")
    
    try:
        # 调用接口获取数据
        api_data = api_client.get_daily_chance(stock_code)
        
        if not api_data:
            logger.warning(f"未获取到数据: {stock_code}")
            return {
                'code': stock_code,
                'name': stock_name,
                'status': 'no_data',
                'count': 0
            }
        
        # 保存数据
        saved_count = save_daily_chance_data(stock_code, stock_name, stock_nature, api_data)
        
        logger.info(f"✅ 完成: {stock_code} ({stock_name}) - 保存了 {saved_count} 条记录")
        
        return {
            'code': stock_code,
            'name': stock_name,
            'status': 'success',
            'count': saved_count
        }
        
    except Exception as e:
        logger.error(f"❌ 失败: {stock_code} ({stock_name}) - {e}", exc_info=True)
        return {
            'code': stock_code,
            'name': stock_name,
            'status': 'error',
            'error': str(e),
            'count': 0
        }


def main(test_limit: int = None, batch_size: int = 10, batch_rest: int = 30):
    """
    主函数
    
    Args:
        test_limit: 测试数量限制，None表示处理所有股票
        batch_size: 每批处理的股票数量，默认10个
        batch_rest: 每批之间的休息时间（秒），默认30秒
    """
    logger.info("=" * 80)
    logger.info("开始同步全部A股每日机会数据")
    logger.info("=" * 80)
    
    # 获取股票列表
    logger.info(f"正在获取股票列表{f'（限制{test_limit}支）' if test_limit else ''}...")
    stocks = get_all_active_stocks(limit=test_limit)
    
    if not stocks:
        logger.error("未获取到股票列表")
        return
    
    logger.info(f"✓ 获取到 {len(stocks)} 只股票")
    logger.info(f"⚙️ 批处理设置: 每{batch_size}个股票休息{batch_rest}秒")
    logger.info("-" * 80)
    
    # 初始化API客户端
    api_client = DailyChanceApiClient()
    
    # 统计信息
    total_stocks = len(stocks)
    success_count = 0
    fail_count = 0
    no_data_count = 0
    total_records = 0
    
    start_time = time.time()
    
    # 遍历股票
    for i, stock in enumerate(stocks, 1):
        stock_code = stock['code']
        stock_name = stock['name']
        stock_nature = stock['nature']
        
        logger.info(f"\n[{i}/{total_stocks}] 处理股票: {stock_code} ({stock_name}) - 股性: {stock_nature}")
        
        # 同步数据
        result = sync_single_stock(stock_code, stock_name, stock_nature, api_client)
        
        # 统计
        if result['status'] == 'success':
            success_count += 1
            total_records += result['count']
        elif result['status'] == 'no_data':
            no_data_count += 1
        else:
            fail_count += 1
        
        # 每处理batch_size个股票后，休息batch_rest秒（保护接口）
        if i % batch_size == 0 and i < total_stocks:
            elapsed = time.time() - start_time
            avg_time_per_stock = elapsed / i
            remaining_stocks = total_stocks - i
            estimated_time = remaining_stocks * avg_time_per_stock
            
            logger.info("\n" + "=" * 80)
            logger.info(f"📊 阶段进度: 已完成 {i}/{total_stocks} ({i/total_stocks*100:.1f}%)")
            logger.info(f"✅ 成功: {success_count} | ⚠️ 无数据: {no_data_count} | ❌ 失败: {fail_count}")
            logger.info(f"📝 已保存记录: {total_records}")
            logger.info(f"⏱️ 已用时: {elapsed:.1f}秒 | 预计剩余: {estimated_time:.1f}秒")
            logger.info(f"😴 休息{batch_rest}秒，保护接口...")
            logger.info("=" * 80)
            
            time.sleep(batch_rest)
            logger.info("🔄 继续处理...\n")
        else:
            # 常规间隔，避免请求太快
            if i < total_stocks:
                time.sleep(0.5)
    
    # 输出统计
    elapsed_time = time.time() - start_time
    
    logger.info("\n" + "=" * 80)
    logger.info("🎉 同步完成！")
    logger.info("=" * 80)
    logger.info(f"总股票数: {total_stocks}")
    logger.info(f"成功: {success_count}")
    logger.info(f"无数据: {no_data_count}")
    logger.info(f"失败: {fail_count}")
    logger.info(f"总记录数: {total_records}")
    logger.info(f"耗时: {elapsed_time:.2f}秒 ({elapsed_time/60:.1f}分钟)")
    logger.info(f"平均每股: {elapsed_time/total_stocks:.2f}秒")
    logger.info("=" * 80)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='同步全部A股每日机会数据')
    parser.add_argument('--test', type=int, help='测试模式，指定处理的股票数量（如 --test 5 表示只处理5支股票）')
    parser.add_argument('--batch-size', type=int, default=10, help='每批处理的股票数量，默认10个')
    parser.add_argument('--batch-rest', type=int, default=30, help='每批之间的休息时间（秒），默认30秒')
    
    args = parser.parse_args()
    
    if args.test:
        print(f"[测试模式] 只处理 {args.test} 支股票")
        print(f"[批处理设置] 每{args.batch_size}个股票休息{args.batch_rest}秒")
        main(test_limit=args.test, batch_size=args.batch_size, batch_rest=args.batch_rest)
    else:
        print("[警告] 将处理全部股票，确认要继续吗？(y/n): ", end='')
        confirm = input().strip().lower()
        if confirm == 'y':
            print(f"[批处理设置] 每{args.batch_size}个股票休息{args.batch_rest}秒")
            main(batch_size=args.batch_size, batch_rest=args.batch_rest)
        else:
            print("已取消")

