#!/usr/bin/env python3
import sys
sys.path.insert(0, 'backend')

import pymysql
from domain.services.trading_calendar_service import TradingCalendarService
from datetime import date, timedelta

# 检查交易日历
calendar = TradingCalendarService()
target_date = date(2024, 10, 8)

print("检查2024-10-08前的交易日:")
for i in range(1, 15):
    check_date = target_date - timedelta(days=i)
    is_trading = calendar.is_trading_day(check_date)
    print(f"{check_date}: {'✅ 交易日' if is_trading else '❌ 非交易日'}")

# 检查数据库中是否有这些日期的数据
print("\n检查数据库中是否有这些日期的数据:")

DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

for i in range(1, 15):
    check_date = target_date - timedelta(days=i)
    sql = f"SELECT shou_pan_jia FROM basic_data_sz301039 WHERE DATE(shi_jian) = '{check_date.strftime('%Y-%m-%d')}' AND peroid_type = '1day'"
    cursor.execute(sql)
    row = cursor.fetchone()
    
    if row and row[0]:
        print(f"{check_date}: ✅ 有数据 (收盘价: {float(row[0]):.2f})")
    else:
        print(f"{check_date}: ❌ 无数据")

cursor.close()
conn.close()

