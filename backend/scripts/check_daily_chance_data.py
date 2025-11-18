"""检查daily_chance表的数据"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.persistence.database import DatabaseConnection


def check_daily_chance(stock_code: str, date_str: str):
    """检查指定日期的daily_chance数据"""
    db = DatabaseConnection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        query = """
        SELECT stock_code, date, volume_type, bearish_pattern, bullish_pattern, 
               day_win_ratio_score, total_win_ratio_score
        FROM daily_chance
        WHERE stock_code = %s AND DATE(date) = %s
        """
        cursor.execute(query, (stock_code, date_str))
        row = cursor.fetchone()
        
        if row:
            stock_code, date, volume_type, bearish_pattern, bullish_pattern, day_win_ratio, total_win_ratio = row
            print(f"找到 {stock_code} {date} 的daily_chance数据:")
            print(f"  volume_type: {volume_type}")
            print(f"  bearish_pattern: {bearish_pattern}")
            print(f"  bullish_pattern: {bullish_pattern}")
            print(f"  day_win_ratio_score: {day_win_ratio}")
            print(f"  total_win_ratio_score: {total_win_ratio}")
            
            # 检查是否包含Y
            if volume_type and 'Y' in volume_type:
                print(f"\n  ✓ volume_type包含Y")
            else:
                print(f"\n  ✗ volume_type不包含Y")
            
            # 检查bearish_pattern是否非空
            if bearish_pattern and bearish_pattern.strip():
                print(f"  ✓ bearish_pattern非空")
            else:
                print(f"  ✗ bearish_pattern为空")
        else:
            print(f"未找到 {stock_code} {date_str} 的daily_chance数据")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python check_daily_chance_data.py <股票代码> <日期>")
        print("示例: python check_daily_chance_data.py SZ300564 2025-07-24")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    date_str = sys.argv[2]
    check_daily_chance(stock_code, date_str)

