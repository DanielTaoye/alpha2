"""检查股票数据"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from infrastructure.persistence.database import DatabaseConnection


def check_stock_data(stock_code: str):
    """检查股票数据"""
    print("="*100)
    print(f"检查股票数据: {stock_code}")
    print("="*100)
    
    db = DatabaseConnection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # 查询表名
    table_name = f"basic_data_{stock_code.lower()}"
    
    try:
        # 查询最近10条数据
        query = f"""
        SELECT date, open, close, high, low, pre_close, volume
        FROM `{table_name}`
        WHERE HOUR(date) = 0 AND MINUTE(date) = 0
        ORDER BY date DESC
        LIMIT 10
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print(f"未找到股票 {stock_code} 的数据")
            return
        
        print(f"\n最近10条日线数据:\n")
        print(f"{'日期':<12} {'开盘':<8} {'收盘':<8} {'最高':<8} {'最低':<8} {'昨收':<8} {'成交量':<12}")
        print("-"*100)
        
        for row in rows:
            date_val, open_val, close_val, high_val, low_val, pre_close_val, volume_val = row
            print(f"{str(date_val):<12} {open_val:<8.2f} {close_val:<8.2f} {high_val:<8.2f} {low_val:<8.2f} {pre_close_val if pre_close_val else 'NULL':<8} {volume_val:<12}")
        
        # 检查pre_close是否为NULL
        query_null = f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN pre_close IS NULL OR pre_close = 0 THEN 1 ELSE 0 END) as null_count
        FROM `{table_name}`
        WHERE HOUR(date) = 0 AND MINUTE(date) = 0
        """
        cursor.execute(query_null)
        result = cursor.fetchone()
        total, null_count = result
        
        print(f"\n统计信息:")
        print(f"  总日线数据: {total}条")
        print(f"  pre_close为NULL或0: {null_count}条 ({null_count/total*100:.2f}%)")
        
        if null_count > 0:
            print(f"\n警告: pre_close字段有{null_count}条数据为NULL或0，这会导致涨跌幅计算失败！")
            print(f"       乖离率偏离插件需要计算涨跌幅，所以无法触发。")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python check_stock_data.py <股票代码>")
        print("示例: python check_stock_data.py SZ300564")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    check_stock_data(stock_code)

