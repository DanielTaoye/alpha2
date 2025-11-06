# 数据库配置
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'your_password',  # 请修改为实际密码
    'database': 'your_database',  # 请修改为实际数据库名
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

