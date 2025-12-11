"""Redis配置"""
import os

# 默认：本地连外网 Redis；通过环境变量可改为服务器内网
DEFAULT_HOST = "sh-crs-gqaomntf.sql.tencentcdb.com"
DEFAULT_PORT = 25305
DEFAULT_PASSWORD = "6ax6US$p2v8e"

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", DEFAULT_HOST),
    "port": int(os.getenv("REDIS_PORT", DEFAULT_PORT)),
    "db": int(os.getenv("REDIS_DB", 0)),
    "password": os.getenv("REDIS_PASSWORD", DEFAULT_PASSWORD),
    # 是否在字符串上保留原样（便于中文字段）
    "decode_responses": True,
    # 连接超时秒
    "socket_timeout": 5,
}

# 统一的key前缀，便于区分环境
KEY_PREFIX = "alpha:v2"

"""
环境变量快速切换：
- 本地连外网（默认）：无需设置，或显式
  REDIS_HOST=sh-crs-gqaomntf.sql.tencentcdb.com REDIS_PORT=25305
- 服务器连内网：设置
  REDIS_HOST=172.17.0.15 REDIS_PORT=6379
- 密码不同：REDIS_PASSWORD=xxx
"""
