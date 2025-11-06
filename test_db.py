# -*- coding: utf-8 -*-
"""
数据库连接测试脚本 (Windows兼容版)
"""

import pymysql
import sys

# Windows控制台编码设置
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'charset': 'utf8mb4'
}

print("=" * 60)
print("腾讯云数据库连接测试")
print("=" * 60)
print(f"主机: {DB_CONFIG['host']}")
print(f"端口: {DB_CONFIG['port']}")
print(f"用户: {DB_CONFIG['user']}")
print("=" * 60)

try:
    # 测试连接
    print("\n正在连接数据库...")
    conn = pymysql.connect(**DB_CONFIG)
    print("[成功] 数据库连接成功！")
    
    # 获取数据库列表
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()
    
    print("\n可用的数据库：")
    print("-" * 60)
    for idx, db in enumerate(databases, 1):
        print(f"{idx}. {db[0]}")
    
    print("\n" + "=" * 60)
    print("请从上面选择一个数据库名，然后运行：")
    print("  python update_db_name.py 数据库名")
    print("=" * 60)
    
    cursor.close()
    conn.close()
    
except pymysql.err.OperationalError as e:
    print(f"[失败] 连接失败: {e}")
    print("\n可能的原因：")
    print("1. 网络连接问题")
    print("2. 数据库服务未启动")
    print("3. 用户名或密码错误")
    print("4. IP白名单未配置（需要在腾讯云控制台添加本机IP）")
    
except Exception as e:
    print(f"[错误] 发生错误: {e}")

print()

