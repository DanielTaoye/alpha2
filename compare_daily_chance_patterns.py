"""对比 b_daily_chance 表数据（不更新，只查看差异）"""
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


def get_stock_table_name(stock_code: str) -> str:
    """根据股票代码获取表名"""
    return f"basic_data_{stock_code.lower()}"


def compare_stock_patterns(conn, stock_code: str, limit=10):
    """对比指定股票的数据"""
    table_name = get_stock_table_name(stock_code)
    
    try:
        with conn.cursor(DictCursor) as cursor:
            # 获取记录（限制数量）
            query = """
                SELECT id, stock_code, date, volume_type, bullish_pattern, bearish_pattern
                FROM b_daily_chance 
                WHERE stock_code = %s 
                ORDER BY date DESC
                LIMIT %s
            """
            cursor.execute(query, (stock_code, limit))
            records = cursor.fetchall()
            
            if not records:
                print(f"股票 {stock_code} 没有记录")
                return
            
            print(f"\n{'='*100}")
            print(f"股票: {stock_code} (对比最近 {len(records)} 条记录)")
            print(f"{'='*100}")
            
            diff_count = 0
            
            for record in records:
                record_id = record['id']
                date_value = record['date']
                
                # 统一处理日期类型
                if isinstance(date_value, datetime):
                    target_date = date_value
                elif isinstance(date_value, str):
                    target_date = datetime.strptime(date_value, '%Y-%m-%d')
                else:
                    target_date = datetime.combine(date_value, datetime.min.time())
                
                date_str = target_date.strftime('%Y-%m-%d')
                
                # 原有数据
                old_volume = record['volume_type'] or ''
                old_bullish = record['bullish_pattern'] or ''
                old_bearish = record['bearish_pattern'] or ''
                
                try:
                    # 重新计算
                    new_volume = VolumeTypeService.calculate_volume_type(table_name, target_date) or ''
                    
                    bullish_list = BullishPatternService.identify_bullish_patterns(
                        stock_code, table_name, target_date
                    )
                    new_bullish = ','.join(bullish_list) if bullish_list else ''
                    
                    bearish_list = BearishPatternService.identify_bearish_patterns(
                        stock_code, table_name, target_date
                    )
                    new_bearish = ','.join(bearish_list) if bearish_list else ''
                    
                    # 检查是否有差异
                    has_diff = (old_volume != new_volume or 
                               old_bullish != new_bullish or 
                               old_bearish != new_bearish)
                    
                    if has_diff:
                        diff_count += 1
                        print(f"\n日期: {date_str}")
                        print(f"-" * 100)
                        
                        if old_volume != new_volume:
                            print(f"  volume_type:")
                            print(f"    旧: [{old_volume}]")
                            print(f"    新: [{new_volume}]")
                        
                        if old_bullish != new_bullish:
                            print(f"  bullish_pattern:")
                            print(f"    旧: [{old_bullish}]")
                            print(f"    新: [{new_bullish}]")
                        
                        if old_bearish != new_bearish:
                            print(f"  bearish_pattern:")
                            print(f"    旧: [{old_bearish}]")
                            print(f"    新: [{new_bearish}]")
                
                except Exception as e:
                    print(f"\n日期: {date_str} - 计算失败: {e}")
            
            print(f"\n{'='*100}")
            print(f"对比完成: 共 {len(records)} 条记录，{diff_count} 条有差异")
            print(f"{'='*100}")
            
    except Exception as e:
        print(f"对比失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='对比 b_daily_chance 数据（不更新）')
    parser.add_argument('-s', '--stock', required=True, help='股票代码，如: SH600000')
    parser.add_argument('-n', '--limit', type=int, default=10, help='对比记录数（默认10条）')
    
    args = parser.parse_args()
    
    print("=" * 100)
    print("b_daily_chance 数据对比工具")
    print("=" * 100)
    print(f"数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}")
    print(f"股票代码: {args.stock}")
    print(f"对比记录数: {args.limit}")
    print("-" * 100)
    
    # 连接数据库
    try:
        conn = pymysql.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password'],
            database=DATABASE_CONFIG['database'],
            charset=DATABASE_CONFIG['charset']
        )
        print("✓ 数据库连接成功")
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return
    
    try:
        compare_stock_patterns(conn, args.stock, args.limit)
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

