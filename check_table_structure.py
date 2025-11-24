#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查all_stock表的结构
"""

import pymysql

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def main():
    conn = pymysql.connect(**DB_CONFIG)
    
    with conn.cursor() as cursor:
        # 切换到stock数据库
        cursor.execute("USE stock")
        
        # 查看all_stock表结构
        print("all_stock表结构:")
        cursor.execute("DESCRIBE all_stock")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col}")
        
        print("\n前5条数据:")
        cursor.execute("SELECT * FROM all_stock LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row}")
    
    conn.close()

if __name__ == "__main__":
    main()

