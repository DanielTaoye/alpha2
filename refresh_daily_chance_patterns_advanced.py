"""刷新 b_daily_chance 表 - 高级版本（支持指定股票和日期范围）"""
import sys
from pathlib import Path
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
import argparse

# 添加项目路径
backend_dir = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_dir))

from config import DATABASE_CONFIG
from domain.services.volume_type_service import VolumeTypeService
from domain.services.bullish_pattern_service import BullishPatternService
from domain.services.bearish_pattern_service import BearishPatternService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def get_stock_codes(conn, specific_codes=None):
    """获取股票代码列表"""
    try:
        with conn.cursor(DictCursor) as cursor:
            if specific_codes:
                placeholders = ','.join(['%s'] * len(specific_codes))
                query = f"SELECT DISTINCT stock_code FROM b_daily_chance WHERE stock_code IN ({placeholders}) ORDER BY stock_code"
                cursor.execute(query, specific_codes)
            else:
                cursor.execute("SELECT DISTINCT stock_code FROM b_daily_chance ORDER BY stock_code")
            results = cursor.fetchall()
            return [row['stock_code'] for row in results]
    except Exception as e:
        logger.error(f"获取股票代码失败: {e}")
        return []


def get_stock_table_name(stock_code: str) -> str:
    """根据股票代码获取表名"""
    return f"basic_data_{stock_code.lower()}"


def get_daily_chance_records(conn, stock_code: str, start_date=None, end_date=None):
    """获取指定股票的 daily_chance 记录"""
    try:
        with conn.cursor(DictCursor) as cursor:
            if start_date and end_date:
                query = """
                    SELECT id, stock_code, date 
                    FROM b_daily_chance 
                    WHERE stock_code = %s AND date >= %s AND date <= %s
                    ORDER BY date
                """
                cursor.execute(query, (stock_code, start_date, end_date))
            elif start_date:
                query = """
                    SELECT id, stock_code, date 
                    FROM b_daily_chance 
                    WHERE stock_code = %s AND date >= %s
                    ORDER BY date
                """
                cursor.execute(query, (stock_code, start_date))
            elif end_date:
                query = """
                    SELECT id, stock_code, date 
                    FROM b_daily_chance 
                    WHERE stock_code = %s AND date <= %s
                    ORDER BY date
                """
                cursor.execute(query, (stock_code, end_date))
            else:
                query = """
                    SELECT id, stock_code, date 
                    FROM b_daily_chance 
                    WHERE stock_code = %s 
                    ORDER BY date
                """
                cursor.execute(query, (stock_code,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"获取daily_chance记录失败 {stock_code}: {e}")
        return []


def update_daily_chance(conn, record_id: int, volume_type: str, bullish_pattern: str, bearish_pattern: str):
    """更新 b_daily_chance 记录"""
    try:
        with conn.cursor() as cursor:
            query = """
                UPDATE b_daily_chance 
                SET volume_type = %s, 
                    bullish_pattern = %s, 
                    bearish_pattern = %s 
                WHERE id = %s
            """
            cursor.execute(query, (volume_type or '', bullish_pattern or '', bearish_pattern or '', record_id))
        return True
    except Exception as e:
        logger.error(f"更新记录失败 id={record_id}: {e}")
        return False


def refresh_stock_patterns(conn, stock_code: str, start_date=None, end_date=None):
    """刷新指定股票的记录"""
    table_name = get_stock_table_name(stock_code)
    
    # 获取该股票的记录
    records = get_daily_chance_records(conn, stock_code, start_date, end_date)
    
    if not records:
        logger.info(f"股票 {stock_code} 没有符合条件的记录，跳过")
        return 0
    
    logger.info(f"开始处理股票 {stock_code}，共 {len(records)} 条记录")
    
    updated_count = 0
    error_count = 0
    
    for i, record in enumerate(records, 1):
        record_id = record['id']
        date_value = record['date']
        
        # 统一处理日期类型
        if isinstance(date_value, datetime):
            target_date = date_value
        elif isinstance(date_value, str):
            target_date = datetime.strptime(date_value, '%Y-%m-%d')
        else:
            target_date = datetime.combine(date_value, datetime.min.time())
        
        try:
            # 1. 计算成交量类型
            volume_type = VolumeTypeService.calculate_volume_type(table_name, target_date)
            
            # 2. 识别多头组合
            bullish_patterns = BullishPatternService.identify_bullish_patterns(
                stock_code, table_name, target_date
            )
            bullish_pattern_str = ','.join(bullish_patterns) if bullish_patterns else ''
            
            # 3. 识别空头组合
            bearish_patterns = BearishPatternService.identify_bearish_patterns(
                stock_code, table_name, target_date
            )
            bearish_pattern_str = ','.join(bearish_patterns) if bearish_patterns else ''
            
            # 4. 更新数据库
            success = update_daily_chance(
                conn, record_id, 
                volume_type or '', 
                bullish_pattern_str, 
                bearish_pattern_str
            )
            
            if success:
                updated_count += 1
                if updated_count % 50 == 0:
                    conn.commit()
                    logger.info(f"  进度: {i}/{len(records)} ({updated_count} 条已更新)")
            
        except Exception as e:
            error_count += 1
            logger.error(f"处理记录失败 {stock_code} {target_date}: {e}")
            continue
    
    # 提交剩余的更新
    conn.commit()
    
    if error_count > 0:
        logger.warning(f"股票 {stock_code} 处理完成，更新了 {updated_count}/{len(records)} 条记录，{error_count} 条失败")
    else:
        logger.info(f"股票 {stock_code} 处理完成，更新了 {updated_count}/{len(records)} 条记录")
    
    return updated_count


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='刷新 b_daily_chance 表中的 volume_type, bullish_pattern, bearish_pattern')
    parser.add_argument('-s', '--stocks', nargs='+', help='指定股票代码（可多个），如: SH600000 SZ000001')
    parser.add_argument('--start', help='开始日期，格式: YYYY-MM-DD')
    parser.add_argument('--end', help='结束日期，格式: YYYY-MM-DD')
    parser.add_argument('-y', '--yes', action='store_true', help='跳过确认直接执行')
    
    args = parser.parse_args()
    
    # 处理日期参数
    start_date = None
    end_date = None
    
    if args.start:
        try:
            start_date = datetime.strptime(args.start, '%Y-%m-%d')
        except ValueError:
            print(f"错误：开始日期格式不正确: {args.start}，应为 YYYY-MM-DD")
            return
    
    if args.end:
        try:
            end_date = datetime.strptime(args.end, '%Y-%m-%d')
        except ValueError:
            print(f"错误：结束日期格式不正确: {args.end}，应为 YYYY-MM-DD")
            return
    
    print("=" * 80)
    print("刷新 b_daily_chance 表")
    print("=" * 80)
    print(f"数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}")
    
    if args.stocks:
        print(f"指定股票: {', '.join(args.stocks)}")
    else:
        print("处理范围: 所有股票")
    
    if start_date:
        print(f"开始日期: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"结束日期: {end_date.strftime('%Y-%m-%d')}")
    
    print("-" * 80)
    
    # 连接数据库
    try:
        conn = pymysql.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password'],
            database=DATABASE_CONFIG['database'],
            charset=DATABASE_CONFIG['charset'],
            autocommit=False
        )
        print("✓ 数据库连接成功")
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return
    
    try:
        # 获取股票代码列表
        stock_codes = get_stock_codes(conn, args.stocks)
        print(f"✓ 找到 {len(stock_codes)} 只股票")
        
        if not stock_codes:
            print("没有需要处理的股票")
            return
        
        print("-" * 80)
        
        # 询问是否继续
        if not args.yes:
            user_input = input(f"\n是否开始刷新？(y/n): ")
            if user_input.lower() != 'y':
                print("已取消")
                return
        
        print("\n" + "=" * 80)
        print("开始刷新...")
        print("=" * 80)
        
        total_updated = 0
        total_stocks = len(stock_codes)
        
        for idx, stock_code in enumerate(stock_codes, 1):
            print(f"\n[{idx}/{total_stocks}] 处理股票: {stock_code}")
            updated = refresh_stock_patterns(conn, stock_code, start_date, end_date)
            total_updated += updated
        
        print("\n" + "=" * 80)
        print("刷新完成！")
        print("=" * 80)
        print(f"处理股票数: {total_stocks}")
        print(f"更新记录数: {total_updated}")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\n用户中断，正在保存已处理的数据...")
        conn.commit()
        print("已保存")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()
        print("数据库连接已关闭")


if __name__ == "__main__":
    main()

