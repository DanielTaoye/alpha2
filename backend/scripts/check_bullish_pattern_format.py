"""检查多头组合在数据库中的实际存储格式"""
import sys
import os

# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.persistence.database import DatabaseConnection
from datetime import datetime, timedelta
import pymysql.cursors

def check_bullish_pattern_format(stock_code: str):
    """检查多头组合的实际存储格式"""
    # 查询最近有多头组合的记录
    query = """
    SELECT date, bullish_pattern, volume_type
    FROM daily_chance
    WHERE stock_code = %s
    AND bullish_pattern IS NOT NULL
    AND bullish_pattern != ''
    ORDER BY date DESC
    LIMIT 10
    """
    
    conn = None
    try:
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(query, (stock_code,))
        result = cursor.fetchall()
        
        if not result:
            print(f"未找到 {stock_code} 的多头组合数据")
            return
        
        print(f"\n{'='*80}")
        print(f"股票代码: {stock_code} - 多头组合数据格式检查")
        print(f"{'='*80}\n")
        
        for row in result:
            date = row['date']
            bullish_pattern = row['bullish_pattern']
            volume_type = row['volume_type']
            
            print(f"日期: {date}")
            print(f"多头组合: {bullish_pattern}")
            print(f"成交量类型: {volume_type}")
            
            # 检查是否包含1234对应的名称
            pattern_names_1234 = ["十字星+中阳线", "触底反弹阳线+阳线", "触底反弹阴线+中阳", "阳包阴"]
            pattern_list = [p.strip() for p in bullish_pattern.split(',')]
            
            matched_1234 = [p for p in pattern_list if p in pattern_names_1234]
            
            if matched_1234:
                print(f"[YES] 包含1234组合: {', '.join(matched_1234)}")
            else:
                print(f"[NO] 不包含1234组合 (包含其他组合: {', '.join(pattern_list)})")
            
            print("-" * 80)
        
        cursor.close()
            
    except Exception as e:
        print(f"查询失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        stock_code = sys.argv[1]
    else:
        stock_code = "SH600016"
    
    check_bullish_pattern_format(stock_code)

