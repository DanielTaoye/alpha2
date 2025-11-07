"""数据库连接管理"""
import pymysql
from typing import Optional
from contextlib import contextmanager
from infrastructure.config.database_config import DATABASE_CONFIG
from infrastructure.logging.logger import get_database_logger

logger = get_database_logger()


class DatabaseConnection:
    """数据库连接管理器"""
    
    @staticmethod
    def get_connection():
        """获取数据库连接"""
        try:
            logger.debug(f"正在连接数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}")
            connection = pymysql.connect(**DATABASE_CONFIG)
            logger.debug("数据库连接成功")
            return connection
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    @contextmanager
    def get_connection_context():
        """获取数据库连接上下文管理器"""
        connection = None
        try:
            logger.debug("开始数据库事务")
            connection = pymysql.connect(**DATABASE_CONFIG)
            yield connection
            connection.commit()
            logger.debug("数据库事务提交成功")
        except Exception as e:
            if connection:
                connection.rollback()
                logger.error("数据库事务回滚", exc_info=True)
            raise e
        finally:
            if connection:
                connection.close()
                logger.debug("数据库连接已关闭")

