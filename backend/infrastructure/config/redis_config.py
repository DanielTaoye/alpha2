"""Redis配置"""

# 默认本地Redis，后续可改为缓存服务器地址
REDIS_CONFIG = {
    "host": "sh-crs-gqaomntf.sql.tencentcdb.com",
    "port": 25305,
    "db": 0,
    "password": "6ax6US$p2v8e",
    # 是否在字符串上保留原样（便于中文字段）
    "decode_responses": True,
    # 连接超时秒
    "socket_timeout": 5,
}

# 统一的key前缀，便于区分环境
KEY_PREFIX = "alpha:v2"

