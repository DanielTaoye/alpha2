"""
诊断C点计算问题
检查数据和计算逻辑
"""
import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from domain.services.cr_strategy_service import CRStrategyService

logger = get_logger(__name__)


def diagnose_stock(stock_code: str, limit: int = 10):
    """诊断某只股票的C点计算情况"""
    print("=" * 80)
    print(f"诊断股票: {stock_code}")
    print("=" * 80)
    
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            
            # 查询最近的 daily_chance 数据
            sql = """
                SELECT date, volume_type, total_win_ratio_score 
                FROM daily_chance 
                WHERE stock_code = %s 
                ORDER BY date DESC 
                LIMIT %s
            """
            cursor.execute(sql, (stock_code, limit))
            results = cursor.fetchall()
            
            if not results:
                print(f"\n❌ 股票 {stock_code} 在 daily_chance 表中没有数据！")
                return
            
            print(f"\n找到 {len(results)} 条 daily_chance 记录")
            print("\n" + "-" * 80)
            print(f"{'日期':<12} {'成交量类型':<20} {'赔率分':<10} {'胜率分':<10} {'总分':<10} {'触发C点':<10}")
            print("-" * 80)
            
            # 创建策略服务
            strategy_service = CRStrategyService()
            
            triggered_count = 0
            for row in results:
                # 使用索引访问（因为fetchall返回的是tuple）
                date = row[0] if not isinstance(row, dict) else row['date']
                volume_type = row[1] if not isinstance(row, dict) else row['volume_type']
                total_win_ratio_score = row[2] if not isinstance(row, dict) else row['total_win_ratio_score']
                
                # 计算胜率分
                win_rate_score = strategy_service._calculate_win_rate_score(volume_type)
                
                # 计算总分
                win_ratio_score = total_win_ratio_score if total_win_ratio_score is not None else 0
                total_score = win_ratio_score + win_rate_score
                
                # 判断是否触发C点
                is_triggered = total_score >= 70
                if is_triggered:
                    triggered_count += 1
                
                triggered_mark = '[Y]' if is_triggered else '[N]'
                print(f"{date.strftime('%Y-%m-%d'):<12} {volume_type or 'None':<20} {win_ratio_score:<10.2f} {win_rate_score:<10.2f} {total_score:<10.2f} {triggered_mark:<10}")
            
            print("-" * 80)
            print(f"\n[Summary] Recent {len(results)} days: {triggered_count} days triggered C-point (threshold >= 70)")
            
            if triggered_count == 0:
                print("\n[Tips]")
                print("   1. Check if total_win_ratio_score (odds score) is high enough")
                print("   2. Check if volume_type contains ABCD (40 pts) or H (28 pts)")
                print("   3. Total score needs >= 70 to trigger C-point")
                print("\n   Formula: Total = Odds Score + Win Rate Score")
                print("   Win Rate Score:")
                print("      - ABCD (normal volume): 40 pts")
                print("      - H (special): 28 pts")
                print("      - EF (abnormal): 0 pts")
                print("      - Others: 0 pts")
            
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)


def get_sample_stocks(limit: int = 5):
    """获取示例股票"""
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT DISTINCT stock_code, stock_name 
                FROM daily_chance 
                ORDER BY stock_code 
                LIMIT %s
            """
            cursor.execute(sql, (limit,))
            results = cursor.fetchall()
            return results
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}", exc_info=True)
        return []


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("C点诊断工具")
    print("=" * 80)
    
    # 获取示例股票
    stocks = get_sample_stocks(5)
    
    if not stocks:
        print("\n❌ 无法获取股票列表")
        return
    
    print(f"\n找到 {len(stocks)} 只股票，开始诊断...\n")
    
    for stock in stocks:
        stock_code = stock['stock_code'] if isinstance(stock, dict) else stock[0]
        diagnose_stock(stock_code, limit=10)
        print("\n")


if __name__ == "__main__":
    main()

