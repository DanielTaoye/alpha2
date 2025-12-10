"""检查成交量类型"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.persistence.database import DatabaseConnection

def check_volume_types(stock_code: str, start_date: str, end_date: str):
    """查询指定时间段的成交量类型"""
    with DatabaseConnection.get_connection_context() as conn:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 查询daily_chance表的成交量类型
        sql = """
            SELECT DATE(date) as trade_date, volume_type
            FROM b_daily_chance
            WHERE stock_code = %s AND date >= %s AND date <= %s
            ORDER BY date
        """
        cursor.execute(sql, (stock_code, start_date, end_date))
        results = cursor.fetchall()
        
        print(f"\n{'='*80}")
        print(f"股票: {stock_code} 成交量类型查询 ({start_date} 至 {end_date})")
        print(f"{'='*80}")
        print(f"{'日期':<12} {'成交量类型':<20}")
        print(f"{'-'*80}")
        
        for r in results:
            date_str = r['trade_date'].strftime('%Y-%m-%d') if r['trade_date'] else 'N/A'
            volume_type = r['volume_type'] or '-'
            print(f"{date_str:<12} {volume_type:<20}")
        
        # 查询K线表的实际成交量数据
        table_name = f"basic_data_{stock_code.lower()}"
        sql2 = f"""
            SELECT DATE(shi_jian) as trade_date, cheng_jiao_liang as volume
            FROM `{table_name}`
            WHERE DATE(shi_jian) >= %s AND DATE(shi_jian) <= %s 
            AND peroid_type = '1day'
            ORDER BY shi_jian
        """
        cursor.execute(sql2, (start_date, end_date))
        kline_results = cursor.fetchall()
        
        print(f"\n{'='*80}")
        print(f"K线表实际成交量数据")
        print(f"{'='*80}")
        print(f"{'日期':<12} {'成交量':<15}")
        print(f"{'-'*80}")
        
        for r in kline_results:
            date_str = r['trade_date'].strftime('%Y-%m-%d') if r['trade_date'] else 'N/A'
            volume = float(r['volume'] or 0)
            print(f"{date_str:<12} {volume:<15,.0f}")

if __name__ == '__main__':
    check_volume_types('SH600004', '2024-09-25', '2024-10-10')

