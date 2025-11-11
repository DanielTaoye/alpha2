"""同步脚本配置文件

生产环境数据库配置
注意：此文件包含敏感信息，请勿提交到版本控制系统
"""

# 生产环境数据库配置
PROD_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',  # 生产环境主机
    'port': 21648,                                  # 生产环境端口
    'user': 'root',                                 # 生产环境用户名
    'password': 'MrEPYZus7myr',                     # 生产环境密码
    'database': 'stock',                             # 数据库名
    'charset': 'utf8mb4'
}

# 本地数据库配置（如果需要修改）
LOCAL_DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '1234',           # 本地数据库密码
    'database': 'stock',
    'charset': 'utf8mb4'
}

