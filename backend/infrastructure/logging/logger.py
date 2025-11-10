
"""日志配置模块"""
import logging
import os
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """
    获取logger实例
    
    Args:
        name: logger名称
        
    Returns:
        配置好的logger实例
    """
    logger = logging.getLogger(name)
    
    # 如果已经配置过handler，直接返回
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # 确保logs目录存在
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 文件handler
    log_file = os.path.join(log_dir, 'app.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 格式化
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
=======
"""日志配置和管理"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


class LoggerManager:
    """日志管理器"""
    
    _loggers = {}
    
    @classmethod
    def setup_logger(cls, name: str, log_file: str = None, level=logging.INFO):
        """
        设置日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
            level: 日志级别
            
        Returns:
            配置好的日志记录器
        """
        if name in cls._loggers:
            return cls._loggers[name]
        
        # 创建日志记录器
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 避免重复添加处理器
        if logger.handlers:
            return logger
        
        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # 使用RotatingFileHandler，自动轮转日志文件
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,  # 保留5个备份
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def get_logger(cls, name: str):
        """获取已配置的日志记录器"""
        if name not in cls._loggers:
            # 如果没有配置，使用默认配置
            return cls.setup_logger(name)
        return cls._loggers[name]


def get_app_logger():
    """获取应用日志记录器"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs')
    log_file = os.path.join(log_dir, 'app.log')
    return LoggerManager.setup_logger('app', log_file, logging.INFO)


def get_api_logger():
    """获取API日志记录器"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs')
    log_file = os.path.join(log_dir, 'api.log')
    return LoggerManager.setup_logger('api', log_file, logging.INFO)


def get_database_logger():
    """获取数据库日志记录器"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs')
    log_file = os.path.join(log_dir, 'database.log')
    return LoggerManager.setup_logger('database', log_file, logging.INFO)


def get_external_api_logger():
    """获取外部API日志记录器"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs')
    log_file = os.path.join(log_dir, 'external_api.log')
    return LoggerManager.setup_logger('external_api', log_file, logging.INFO)


