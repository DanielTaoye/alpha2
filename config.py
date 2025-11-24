# 数据库配置
DATABASE_CONFIG = {
    'host': '172.17.16.30',  # 腾讯云MySQL内网地址
    'port': 3306,
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
    'debug': True
}

