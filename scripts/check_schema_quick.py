
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
cursor.execute("DESCRIBE market_index_daily")
print(cursor.fetchall())
conn.close()
