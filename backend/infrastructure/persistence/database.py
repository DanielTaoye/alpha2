"""数据库连接管理"""
import pymysql
from typing import Optional
from contextlib import contextmanager
from infrastructure.config.database_config import DATABASE_CONFIG


class DatabaseConnection:
    """数据库连接管理器"""
    
    @staticmethod
    def get_connection():
        """获取数据库连接"""
        return pymysql.connect(**DATABASE_CONFIG)
    
    @staticmethod
    @contextmanager
    def get_connection_context():
        """获取数据库连接上下文管理器"""
        connection = None
        try:
            connection = pymysql.connect(**DATABASE_CONFIG)
            yield connection
            connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            raise e
        finally:
            if connection:
                connection.close()

