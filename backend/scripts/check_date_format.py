"""检查K线日期格式"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection
import pymysql

conn = DatabaseConnection.get_connection()
cursor = conn.cursor(pymysql.cursors.DictCursor)

print("="*60)
print("检查 basic_data_sz002475 的日期格式")
print("="*60)

# 查看日K线
cursor.execute("""
    SELECT shi_jian, peroid_type 
    FROM basic_data_sz002475 
    WHERE peroid_type = '1day'
    ORDER BY shi_jian DESC 
    LIMIT 5
""")
print("\n日K线 (peroid_type='1day'):")
for row in cursor.fetchall():
    print(f"  {row['shi_jian']} (type={type(row['shi_jian'])})")

# 查看30分钟K线
cursor.execute("""
    SELECT shi_jian, peroid_type 
    FROM basic_data_sz002475 
    WHERE peroid_type = '30min'
    ORDER BY shi_jian DESC 
    LIMIT 5
""")
print("\n30分钟K线 (peroid_type='30min'):")
for row in cursor.fetchall():
    print(f"  {row['shi_jian']} (type={type(row['shi_jian'])})")

# 查看特定日期的日K线和30分钟K线
cursor.execute("""
    SELECT shi_jian, peroid_type 
    FROM basic_data_sz002475 
    WHERE shi_jian >= '2024-04-01' AND shi_jian < '2024-04-03'
    ORDER BY shi_jian, peroid_type
    LIMIT 20
""")
print("\n2024-04-01到2024-04-02的K线:")
for row in cursor.fetchall():
    print(f"  {row['shi_jian']} (peroid_type={row['peroid_type']})")

cursor.close()
conn.close()

