# 环境配置自动加载
import os

# 通过环境变量 ENV 判断是本地还是服务器
# 本地开发: ENV=local (默认)
# 服务器生产: ENV=server
ENV = os.getenv('ENV', 'local')

if ENV == 'server':
    # 服务器环境 - 使用内网数据库
    from config_server import DATABASE_CONFIG, EXTERNAL_API, SERVER_CONFIG
    print(f"[配置] 加载服务器环境配置 (数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']})")
else:
    # 本地环境
    from config_local import DATABASE_CONFIG, EXTERNAL_API, SERVER_CONFIG
    print(f"[配置] 加载本地环境配置 (数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']})")

