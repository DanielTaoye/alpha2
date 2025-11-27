"""刷新生产数据库中60支股票的多头和空头组合脚本"""
import sys
import os
from datetime import datetime
from typing import List, Dict
import pymysql

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from domain.services.bullish_pattern_service import BullishPatternService
from domain.services.bearish_pattern_service import BearishPatternService
from domain.models.stock import StockGroups
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# 生产数据库配置
PROD_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def get_60_stocks() -> List[Dict]:
    """获取60支股票信息"""
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    stocks = []
    for group_name, stock_list in all_groups.items():
        for stock in stock_list:
            stocks.append({
                'code': stock.code,
                'name': stock.name,
                'table': stock.table_name,
                'nature': group_name
            })
    
    logger.info(f"从配置中获取到 {len(stocks)} 只股票")
    return stocks


def get_stock_dates_from_db(connection, stock_code: str) -> List[datetime]:
    """从生产数据库获取该股票在daily_chance表中的所有日期"""
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT DISTINCT date 
                FROM b_daily_chance 
                WHERE stock_code = %s 
                ORDER BY date ASC
            """
            cursor.execute(query, (stock_code,))
            results = cursor.fetchall()
            
            dates = [row['date'] for row in results if row['date']]
            logger.info(f"股票 {stock_code} 在生产库中有 {len(dates)} 条记录")
            return dates
            
    except Exception as e:
        logger.error(f"查询股票 {stock_code} 日期失败: {e}")
        return []


def update_patterns_batch(connection, updates: List[tuple]) -> int:
    """批量更新多头和空头组合"""
    try:
        with connection.cursor() as cursor:
            # 批量更新SQL
            update_sql = """
                UPDATE b_daily_chance 
                SET bullish_pattern = %s, bearish_pattern = %s 
                WHERE stock_code = %s AND date = %s
            """
            
            # 执行批量更新
            affected_rows = cursor.executemany(update_sql, updates)
            connection.commit()
            
            return affected_rows
            
    except Exception as e:
        logger.error(f"批量更新失败: {e}")
        connection.rollback()
        return 0


def calculate_and_update_stock_patterns(
    connection,
    stock_code: str,
    stock_name: str,
    table_name: str
) -> int:
    """
    计算并更新单个股票的多头和空头组合
    
    Args:
        connection: 数据库连接
        stock_code: 股票代码
        stock_name: 股票名称
        table_name: K线表名
        
    Returns:
        更新的记录数
    """
    try:
        logger.info(f"开始处理股票: {stock_code} ({stock_name})")
        
        # 获取该股票在daily_chance表中的所有日期
        dates = get_stock_dates_from_db(connection, stock_code)
        
        if not dates:
            logger.warning(f"股票 {stock_code} 在生产库中没有数据")
            return 0
        
        logger.info(f"股票 {stock_code} 共有 {len(dates)} 条记录需要计算")
        
        # 准备批量更新数据
        updates = []
        success_count = 0
        error_count = 0
        
        for date in dates:
            try:
                # 计算多头组合
                bullish_patterns = BullishPatternService.identify_bullish_patterns(
                    stock_code=stock_code,
                    table_name=table_name,
                    target_date=date
                )
                bullish_pattern_str = ','.join(bullish_patterns) if bullish_patterns else ''
                
                # 计算空头组合
                bearish_patterns = BearishPatternService.identify_bearish_patterns(
                    stock_code=stock_code,
                    table_name=table_name,
                    target_date=date
                )
                bearish_pattern_str = ','.join(bearish_patterns) if bearish_patterns else ''
                
                # 添加到更新列表
                date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date)
                updates.append((bullish_pattern_str, bearish_pattern_str, stock_code, date_str))
                success_count += 1
                
                # 每1000条记录输出一次进度
                if success_count % 1000 == 0:
                    logger.info(f"  已计算 {success_count}/{len(dates)} 条记录...")
                    
            except Exception as e:
                logger.error(f"计算日期 {date} 的组合失败: {e}")
                error_count += 1
        
        if not updates:
            logger.warning(f"股票 {stock_code} 没有需要更新的记录")
            return 0
        
        # 批量更新到数据库
        logger.info(f"开始批量更新 {len(updates)} 条记录到生产库...")
        updated_count = update_patterns_batch(connection, updates)
        
        logger.info(f"股票 {stock_code} 完成: 成功计算{success_count}条, 失败{error_count}条, 更新{updated_count}条")
        
        return updated_count
        
    except Exception as e:
        logger.error(f"处理股票 {stock_code} 失败: {e}", exc_info=True)
        return 0


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("开始刷新生产数据库中60支股票的多头和空头组合")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"目标数据库: {PROD_DB_CONFIG['host']}:{PROD_DB_CONFIG['port']}")
    logger.info("=" * 80)
    
    connection = None
    
    try:
        # 连接生产数据库
        logger.info("正在连接生产数据库...")
        connection = pymysql.connect(**PROD_DB_CONFIG)
        logger.info("生产数据库连接成功！")
        
        # 获取60支股票
        stocks = get_60_stocks()
        logger.info(f"共需要处理 {len(stocks)} 只股票")
        
        # 统计信息
        total_updated = 0
        success_count = 0
        failed_stocks = []
        
        # 处理每只股票
        for i, stock in enumerate(stocks, 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"[{i}/{len(stocks)}] 处理股票: {stock['code']} ({stock['name']})")
            logger.info(f"{'='*80}")
            
            try:
                updated = calculate_and_update_stock_patterns(
                    connection=connection,
                    stock_code=stock['code'],
                    stock_name=stock['name'],
                    table_name=stock['table']
                )
                
                if updated > 0:
                    total_updated += updated
                    success_count += 1
                    logger.info(f"✓ 股票 {stock['code']} 处理成功，更新了 {updated} 条记录")
                else:
                    logger.warning(f"✗ 股票 {stock['code']} 没有更新任何记录")
                    
            except Exception as e:
                logger.error(f"✗ 处理股票 {stock['code']} 失败: {e}", exc_info=True)
                failed_stocks.append(stock['code'])
        
        # 输出结果
        logger.info("\n" + "=" * 80)
        logger.info("刷新完成！")
        logger.info("=" * 80)
        logger.info(f"总股票数: {len(stocks)}")
        logger.info(f"成功处理: {success_count} 只")
        logger.info(f"失败: {len(failed_stocks)} 只")
        logger.info(f"总更新记录数: {total_updated}")
        
        if failed_stocks:
            logger.warning(f"失败的股票列表: {', '.join(failed_stocks)}")
        else:
            logger.info("✓ 所有股票都已成功处理！")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"刷新失败: {str(e)}", exc_info=True)
        sys.exit(1)
        
    finally:
        # 关闭数据库连接
        if connection:
            connection.close()
            logger.info("生产数据库连接已关闭")


if __name__ == '__main__':
    main()

