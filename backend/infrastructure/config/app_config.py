"""应用配置"""

SERVER_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': True
}

# 周期类型映射（数据库字段值）
PERIOD_TYPE_MAP = {
    '30min': '30min',
    'day': '1day',
    'week': 'week',
    'month': 'month'
}

# 时间范围配置（不同周期的数据范围，单位：天）
TIME_RANGE_CONFIG = {
    '30min': 90,    # 30分钟K线：最近3个月
    'day': 730,     # 日K线：最近2年
    'week': 1095,   # 周K线：最近3年
    'month': 1825   # 月K线：最近5年
}

