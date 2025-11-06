# 配置文件示例
# 使用前请复制此文件为 config_local.py 并修改相应配置

# 数据库配置
DATABASE_CONFIG = {
    'host': 'localhost',        # 数据库主机地址
    'port': 3306,              # 数据库端口
    'user': 'root',            # 数据库用户名
    'password': '123456',      # 数据库密码（请修改）
    'database': 'stock_db',    # 数据库名（请修改）
    'charset': 'utf8mb4'
}

# 外部API配置
EXTERNAL_API = {
    'url': 'https://apiprod.mtygs.cn/api/stock/getStockAnalysis',
    'token': '2025102013283854160ae6136c47da8d6c065f7919e66a_17721044150',  # 可能需要更新
    'timeout': 10  # 请求超时时间（秒）
}

# 服务器配置
SERVER_CONFIG = {
    'host': '0.0.0.0',    # 0.0.0.0 表示监听所有网卡
    'port': 5000,         # 服务端口
    'debug': True         # 开发模式，生产环境请设置为False
}

# 股票表名映射（如果实际表名与默认不同，请在此修改）
STOCK_TABLE_MAPPING = {
    'SZ300188': 'basic_data_sz300188',
    'SH603556': 'basic_data_sh603556',
    'SZ002130': 'basic_data_sz002130',
    'SH600037': 'basic_data_sh600037',
    'SZ301039': 'basic_data_sz301039',
    'SH600004': 'basic_data_sh600004',
    'SZ300443': 'basic_data_sz300443',
    'SH600889': 'basic_data_sh600889',
    'SH688512': 'basic_data_sh688512',
    'SH688693': 'basic_data_sh688693',
    'SZ002475': 'basic_data_sz002475',
    'SZ300750': 'basic_data_sz300750',
    'SH601288': 'basic_data_sh601288',
    'SH601857': 'basic_data_sh601857',
    'SH601899': 'basic_data_sh601899'
}

