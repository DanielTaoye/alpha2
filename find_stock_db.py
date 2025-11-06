#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查找包含 stock 相关表的数据库
"""
import pymysql

def find_stock_databases():
    """查找所有包含 stock 相关表的数据库"""
    try:
        # 连接到 MySQL 服务器（不指定数据库）
        conn = pymysql.connect(
            host='localhost',
            port=3306,
            user='root',
            password='1234',
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        print("正在搜索本地 MySQL 中的所有数据库...")
        print("=" * 60)
        
        # 获取所有数据库
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        
        print(f"\n找到 {len(databases)} 个数据库：")
        for db in databases:
            print(f"  - {db[0]}")
        
        print("\n" + "=" * 60)
        print("正在搜索包含 'stock' 或股票相关表的数据库...\n")
        
        stock_dbs = []
        
        for db in databases:
            db_name = db[0]
            # 跳过系统数据库
            if db_name in ['information_schema', 'mysql', 'performance_schema', 'sys']:
                continue
            
            try:
                cursor.execute(f"USE `{db_name}`")
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                
                # 查找包含 stock 或 basic_data 的表
                stock_tables = [t[0] for t in tables if 'stock' in t[0].lower() or 'basic_data' in t[0].lower()]
                
                if stock_tables:
                    stock_dbs.append((db_name, stock_tables))
                    print(f"[找到] 数据库: {db_name}")
                    print(f"  包含 {len(stock_tables)} 个相关表:")
                    for table in stock_tables[:10]:  # 只显示前10个
                        print(f"    - {table}")
                    if len(stock_tables) > 10:
                        print(f"    ... 还有 {len(stock_tables) - 10} 个表")
                    print()
                    
            except Exception as e:
                print(f"  [跳过] {db_name}: {e}")
        
        if not stock_dbs:
            print("[提示] 未找到包含 stock 相关表的数据库")
            print("\n建议：")
            print("1. 确认股票数据是否已导入到 MySQL")
            print("2. 确认数据库名称和表名称是否正确")
        else:
            print("=" * 60)
            print(f"\n总结: 找到 {len(stock_dbs)} 个包含股票数据的数据库")
            print("\n推荐配置:")
            if stock_dbs:
                db_name, tables = stock_dbs[0]
                print(f"  database: '{db_name}'")
                print(f"  (包含 {len(tables)} 个股票相关表)")
        
        cursor.close()
        conn.close()
        
    except pymysql.Error as e:
        print(f"\n[错误] 连接失败: {e}")
        print("\n请检查:")
        print("1. MySQL 服务是否已启动")
        print("2. 用户名密码是否正确")
    except Exception as e:
        print(f"\n[错误] {e}")

if __name__ == '__main__':
    find_stock_db()

