"""数据库连接管理"""
import pymysql
from typing import Optional
from contextlib import contextmanager
import time
from infrastructure.config.database_config import DATABASE_CONFIG
from infrastructure.logging.logger import get_database_logger

logger = get_database_logger()


class DatabaseConnection:
    """数据库连接管理器"""
    
    @staticmethod
    def get_connection():
        """获取数据库连接"""
        logger.debug(f"正在连接数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}")
        # 默认超时：兼顾“不要无限卡死”和“VPN慢时也能连上”
        cfg = dict(DATABASE_CONFIG)
        cfg.setdefault('connect_timeout', 30)
        cfg.setdefault('read_timeout', 30)
        cfg.setdefault('write_timeout', 30)

        # 针对偶发网络抖动做一次轻量重试（不做指数退避，避免拖慢整体）
        last_err = None
        for attempt in range(2):
            try:
                connection = pymysql.connect(**cfg)
                logger.debug("数据库连接成功")
                return connection
            except Exception as e:
                last_err = e
                logger.error(f"数据库连接失败(attempt={attempt+1}/2): {str(e)}", exc_info=True)
                if attempt == 0:
                    time.sleep(0.6)
        raise last_err
    
    @staticmethod
    @contextmanager
    def get_connection_context():
        """获取数据库连接上下文管理器"""
        connection = None
        try:
            logger.debug("开始数据库事务")
            cfg = dict(DATABASE_CONFIG)
            cfg.setdefault('connect_timeout', 30)
            cfg.setdefault('read_timeout', 30)
            cfg.setdefault('write_timeout', 30)

            last_err = None
            for attempt in range(2):
                try:
                    connection = pymysql.connect(**cfg)
                    break
                except Exception as e:
                    last_err = e
                    logger.error(f"数据库连接失败(事务, attempt={attempt+1}/2): {str(e)}", exc_info=True)
                    if attempt == 0:
                        time.sleep(0.6)
            if connection is None:
                raise last_err
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

