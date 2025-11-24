"""测试配置加载"""
import os

print("=" * 60)
print("配置测试工具")
print("=" * 60)

# 显示当前环境变量
current_env = os.getenv('ENV', 'local')
print(f"当前环境变量: ENV={current_env}")
print("-" * 60)

# 加载配置
from config import DATABASE_CONFIG, EXTERNAL_API, SERVER_CONFIG

print("\n数据库配置:")
print(f"  主机: {DATABASE_CONFIG['host']}")
print(f"  端口: {DATABASE_CONFIG['port']}")
print(f"  用户: {DATABASE_CONFIG['user']}")
print(f"  密码: {'*' * len(DATABASE_CONFIG['password'])}")
print(f"  数据库: {DATABASE_CONFIG['database']}")

print("\n服务器配置:")
print(f"  主机: {SERVER_CONFIG['host']}")
print(f"  端口: {SERVER_CONFIG['port']}")
print(f"  调试: {SERVER_CONFIG['debug']}")

print("\nAPI配置:")
print(f"  URL: {EXTERNAL_API['url']}")
print(f"  Token: {EXTERNAL_API['token'][:20]}...")

print("\n" + "=" * 60)
print("配置加载测试完成")
print("=" * 60)

# 测试数据库连接
print("\n测试数据库连接...")
try:
    import pymysql
    conn = pymysql.connect(
        host=DATABASE_CONFIG['host'],
        port=DATABASE_CONFIG['port'],
        user=DATABASE_CONFIG['user'],
        password=DATABASE_CONFIG['password'],
        database=DATABASE_CONFIG['database'],
        charset=DATABASE_CONFIG['charset'],
        connect_timeout=5
    )
    print("✓ 数据库连接成功！")
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM all_stock")
    count = cursor.fetchone()[0]
    print(f"✓ 找到 {count} 只股票")
    
    conn.close()
except Exception as e:
    print(f"✗ 数据库连接失败: {e}")

print("=" * 60)

