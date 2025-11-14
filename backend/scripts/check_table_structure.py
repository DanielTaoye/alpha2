"""检查表结构"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection

with DatabaseConnection.get_connection_context() as conn:
    cursor = conn.cursor()
    cursor.execute("DESCRIBE basic_data_sz002130")
    columns = cursor.fetchall()
    
    print("basic_data_sz002130 表结构：\n")
    print(f"{'Field':<20} {'Type':<20} {'Null':<10} {'Key':<10}")
    print("=" * 70)
    for col in columns:
        if isinstance(col, dict):
            print(f"{col['Field']:<20} {col['Type']:<20} {col['Null']:<10} {col['Key']:<10}")
        else:
            print(col)

