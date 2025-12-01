# 生产主库配置（可写，外网访问）
DATABASE_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',  # 腾讯云生产主库外网地址
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# API配置
EXTERNAL_API = {
    'url': 'https://apiprod.mtygs.cn/api/stock/getStockAnalysis',
    'token': '2025102013283854160ae6136c47da8d6c065f7919e66a_17721044150'
}

# 服务器配置
SERVER_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': False
}

