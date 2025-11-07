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

