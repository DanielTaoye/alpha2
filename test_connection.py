"""
数据库连接测试脚本
用于快速测试腾讯云数据库连接是否正常
"""

import pymysql

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
    print("✓ 数据库连接成功！")
    
    # 获取数据库列表
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()
    
    print("\n可用的数据库：")
    print("-" * 60)
    for idx, db in enumerate(databases, 1):
        print(f"{idx}. {db[0]}")
    
    # 获取当前用户权限
    cursor.execute("SELECT USER(), DATABASE()")
    result = cursor.fetchone()
    print("\n当前连接信息：")
    print(f"用户: {result[0]}")
    print(f"数据库: {result[1] if result[1] else '未选择'}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✓ 连接测试完成！")
    print("=" * 60)
    print("\n请选择一个数据库，然后修改 backend/app.py 文件中的：")
    print("  database: 'your_database'  ← 改成上面列出的数据库名")
    print("=" * 60)
    
except pymysql.err.OperationalError as e:
    print(f"✗ 连接失败：{e}")
    print("\n可能的原因：")
    print("1. 网络连接问题")
    print("2. 数据库服务未启动")
    print("3. 用户名或密码错误")
    print("4. IP白名单未配置")
    
except Exception as e:
    print(f"✗ 发生错误：{e}")

print("\n")

