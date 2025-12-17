import os
from typing import Dict

import pymysql


def get_db_config() -> Dict:
    """获取数据库连接配置，默认使用生产主库，可通过环境变量覆盖。"""
    return {
        "host": os.getenv("DZH_DB_HOST", "sh-cdb-2hxu41ka.sql.tencentcdb.com"),
        "port": int(os.getenv("DZH_DB_PORT", "21648")),
        "user": os.getenv("DZH_DB_USER", "root"),
        "password": os.getenv("DZH_DB_PASSWORD", "MrEPYZus7myr"),
        "database": os.getenv("DZH_DB_NAME", "stock"),
        "charset": os.getenv("DZH_DB_CHARSET", "utf8mb4"),
    }


def get_connection() -> pymysql.connections.Connection:
    """获取数据库连接。"""
    return pymysql.connect(**get_db_config())

