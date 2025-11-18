"""显示表结构"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.persistence.database import DatabaseConnection


def show_table_structure(table_name):
    """显示表结构"""
    db = DatabaseConnection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"DESCRIBE `{table_name}`")
        columns = cursor.fetchall()
        
        print(f"表 {table_name} 的结构:")
        print(f"{'列名':<20} {'类型':<20} {'NULL':<5} {'键':<5} {'默认值':<10}")
        print("-"*70)
        for col in columns:
            field, type, null, key, default, extra = col
            print(f"{field:<20} {type:<20} {null:<5} {key:<5} {str(default):<10}")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python show_table_structure.py <表名>")
        sys.exit(1)
    
    table_name = sys.argv[1]
    show_table_structure(table_name)

