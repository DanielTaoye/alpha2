#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查basic_data表的结构
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
        
        # 从all_stock获取第一个股票代码
        cursor.execute("SELECT code FROM all_stock LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            code = result['code']
            table_name = f"basic_data_{code.lower()}"
            
            print(f"检查表: {table_name}")
            
            # 检查表是否存在
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if cursor.fetchone():
                print(f"\n{table_name}表结构:")
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                for col in columns:
                    print(f"  {col['Field']}: {col['Type']}")
                
                print(f"\n前3条数据:")
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"  {row}")
            else:
                print(f"表 {table_name} 不存在")
                
                # 尝试查找类似的表
                print("\n查找所有basic_开头的表:")
                cursor.execute("SHOW TABLES LIKE 'basic_%'")
                tables = cursor.fetchall()
                for i, table in enumerate(tables[:5]):
                    print(f"  {list(table.values())[0]}")
    
    conn.close()

if __name__ == "__main__":
    main()

