#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试本地数据库连接和表结构
"""
import pymysql
from config import DATABASE_CONFIG

def test_connection():
    """测试数据库连接"""
    try:
        print("正在连接数据库...")
        print(f"主机: {DATABASE_CONFIG['host']}")
        print(f"端口: {DATABASE_CONFIG['port']}")
        print(f"数据库: {DATABASE_CONFIG['database']}")
        print(f"用户: {DATABASE_CONFIG['user']}")
        print("-" * 50)
        
        conn = pymysql.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        print("[OK] 数据库连接成功！\n")
        
        # 查看所有表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        print(f"数据库中的表（共 {len(tables)} 个）：")
        for table in tables:
            print(f"  - {table[0]}")
        
        print("\n" + "-" * 50)
        
        # 如果存在 stock 表，查看表结构
        table_names = [table[0] for table in tables]
        
        if 'stock' in table_names:
            print("\n检查 'stock' 表结构：")
            cursor.execute("DESCRIBE stock")
            columns = cursor.fetchall()
            print(f"\n表字段（共 {len(columns)} 个）：")
            for col in columns:
                print(f"  - {col[0]} ({col[1]})")
            
            # 查看数据量
            cursor.execute("SELECT COUNT(*) FROM stock")
            count = cursor.fetchone()[0]
            print(f"\n表中数据行数: {count}")
            
            if count > 0:
                print("\n前5条数据样例：")
                cursor.execute("SELECT * FROM stock LIMIT 5")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"  {row}")
        else:
            print("\n[警告] 未找到 'stock' 表")
            print("请确认表名是否正确")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 50)
        print("测试完成！")
        
    except pymysql.Error as e:
        print(f"\n[错误] 数据库连接失败！")
        print(f"错误信息: {e}")
        print("\n请检查：")
        print("1. MySQL服务是否已启动")
        print("2. 数据库名称、用户名、密码是否正确")
        print("3. 数据库 'bendi' 是否存在")
    except Exception as e:
        print(f"\n[错误] 发生错误: {e}")

if __name__ == '__main__':
    test_connection()

