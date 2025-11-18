"""列出数据库中的股票表"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.persistence.database import DatabaseConnection


def list_stock_tables(keyword=None):
    """列出股票表"""
    db = DatabaseConnection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # 查询所有表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        if keyword:
            tables = [t for t in tables if keyword.lower() in t[0].lower()]
        
        print(f"找到 {len(tables)} 个表:")
        for i, (table_name,) in enumerate(tables[:50], 1):  # 只显示前50个
            print(f"  {i}. {table_name}")
        
        if len(tables) > 50:
            print(f"  ... 还有 {len(tables)-50} 个表")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    keyword = sys.argv[1] if len(sys.argv) > 1 else None
    list_stock_tables(keyword)

