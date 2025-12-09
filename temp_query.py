#!/usr/bin/env python3
import pymysql

conn = pymysql.connect(
    host='sh-cdb-2hxu41ka.sql.tencentcdb.com',
    port=21648,
    user='root',
    password='MrEPYZus7myr',
    database='stock',
    charset='utf8mb4'
)
cursor = conn.cursor()

sql = "SELECT shi_jian FROM basic_data_sz301039 WHERE DATE(shi_jian) <= '2024-10-08' AND peroid_type = '1day' ORDER BY shi_jian DESC LIMIT 10"
cursor.execute(sql)
rows = cursor.fetchall()

print('中集车辆最近的交易日数据:')
for row in rows:
    print(row[0])

cursor.close()
conn.close()
