"""检查数据库表"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection

with DatabaseConnection.get_connection_context() as conn:
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES LIKE '%daily%'")
    tables = cursor.fetchall()
    print("包含'daily'的表：")
    for table in tables:
        if isinstance(table, dict):
            print(f"  - {list(table.values())[0]}")
        else:
            print(f"  - {table}")

