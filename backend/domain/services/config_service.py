"""
配置管理服务
负责读取和保存策略配置
"""
import json
import os
from datetime import datetime
from typing import Dict, Any
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

class ConfigService:
    """配置管理服务"""
    
    def __init__(self):
        # 配置文件路径
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config',
            'strategy_config.json'
        )
        self._config_cache = None
        self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
                    logger.info(f"配置加载成功: {self.config_path}")
            else:
                # 如果配置文件不存在，使用默认配置
                self._config_cache = {
                    "strategy1": {
                        "c_point_threshold": 70,
                        "description": "策略1 C点触发阈值（基于赔率分+胜率分+插件）"
                    },
                    "strategy2": {
                        "c_point_threshold": 20,
                        "description": "策略2 C点触发阈值（基于MA+MACD+成交量+K线组合）"
                    },
                    "market_type": "bull",
                    "market_type_description": "市场类型：bull=牛市, bear=熊市（人工判断）",
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self._save_config()
                logger.warning(f"配置文件不存在，已创建默认配置: {self.config_path}")
            
            return self._config_cache
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            # 返回默认配置
            return {
                "strategy1": {"c_point_threshold": 70},
                "strategy2": {"c_point_threshold": 20}
            }
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_cache, f, ensure_ascii=False, indent=2)
            
            logger.info(f"配置保存成功: {self.config_path}")
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            raise
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        if self._config_cache is None:
            self._load_config()
        return self._config_cache
    
    def get_strategy1_threshold(self) -> float:
        """获取策略1的C点触发阈值"""
        config = self.get_config()
        return float(config.get('strategy1', {}).get('c_point_threshold', 70))
    
    def get_strategy2_threshold(self) -> float:
        """获取策略2的C点触发阈值"""
        config = self.get_config()
        return float(config.get('strategy2', {}).get('c_point_threshold', 20))
    
    def get_market_type(self) -> str:
        """获取市场类型"""
        config = self.get_config()
        return config.get('market_type', 'bull')
    
    def update_config(self, strategy1_threshold: float = None, strategy2_threshold: float = None, market_type: str = None) -> Dict[str, Any]:
        """更新配置"""
        config = self.get_config()
        
        if strategy1_threshold is not None:
            config['strategy1']['c_point_threshold'] = strategy1_threshold
            logger.info(f"策略1阈值更新为: {strategy1_threshold}")
        
        if strategy2_threshold is not None:
            config['strategy2']['c_point_threshold'] = strategy2_threshold
            logger.info(f"策略2阈值更新为: {strategy2_threshold}")
        
        if market_type is not None:
            if market_type not in ['bull', 'bear']:
                raise ValueError(f"无效的市场类型: {market_type}，必须是 'bull' 或 'bear'")
            config['market_type'] = market_type
            logger.info(f"市场类型更新为: {market_type}")
        
        config['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self._config_cache = config
        self._save_config()
        
        return config
    
    def reload_config(self):
        """重新加载配置（用于热更新）"""
        self._config_cache = None
        self._load_config()
        logger.info("配置已重新加载")


# 全局单例
_config_service_instance = None

def get_config_service() -> ConfigService:
    """获取配置服务单例"""
    global _config_service_instance
    if _config_service_instance is None:
        _config_service_instance = ConfigService()
    return _config_service_instance

