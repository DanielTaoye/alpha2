
import pymysql

conn = pymysql.connect(
    host='sh-cdb-2hxu41ka.sql.tencentcdb.com',
    port=21648,
    user='root',
    password='MrEPYZus7myr',
    database='stock',
    charset='utf8mb4',
    connect_timeout=10
)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM market_index_daily")
count = cursor.fetchone()[0]
print(f"Total Records: {count}")

cursor.execute("SELECT * FROM market_index_daily ORDER BY trade_date DESC LIMIT 5")
rows = cursor.fetchall()
print("Latest 5 records:")
for r in rows:
    print(r)

conn.close()
