"""
配置管理服务
负责读取和保存策略配置
"""
import json
import os
from datetime import datetime, date
from typing import Dict, Any, Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# 市场类型日期切换点：2025-02-05（不含）之前=熊市，含当天及之后=牛市
MARKET_TYPE_CUTOFF = datetime(2025, 2, 5).date()


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
    
    @staticmethod
    def _normalize_nature(stock_nature: Optional[str]) -> Optional[str]:
        """标准化股性字符串"""
        if not stock_nature:
            return None
        mapping = {
            "短": "短线",
            "短线": "短线",
            "波段": "波段",
            "中线": "中长线",
            "长线": "中长线",
            "中长": "中长线",
            "中长线": "中长线",
        }
        return mapping.get(stock_nature, stock_nature)
    
    @staticmethod
    def _normalize_threshold_value(value: Any, fallback: float) -> float:
        """
        统一处理阈值：
        - 非法格式 -> fallback
        - ≥101 视为“禁用该策略/股性阈值”，返回一个极大值以保证永不触发
        """
        try:
            v = float(value)
        except (TypeError, ValueError):
            return fallback
        if v >= 101:
            return 1e9  # 认为禁用
        return v

    def _get_nature_threshold(self, strategy_key: str, stock_nature: Optional[str], fallback: float) -> float:
        """根据股性获取阈值，未命中则返回fallback"""
        config = self.get_config()
        strategy_cfg = config.get(strategy_key, {}) if isinstance(config, dict) else {}
        nature_thresholds = strategy_cfg.get('nature_thresholds') or {}
        nature = self._normalize_nature(stock_nature)
        
        if nature and nature in nature_thresholds and nature_thresholds[nature] is not None:
            val = self._normalize_threshold_value(nature_thresholds[nature], fallback)
            if val == 1e9:
                logger.info(f"{strategy_key} 股性[{nature}] 阈值设为禁用(>=101)")
            return val
        
        if '波段' in nature_thresholds and nature_thresholds['波段'] is not None:
            val = self._normalize_threshold_value(nature_thresholds['波段'], fallback)
            if val == 1e9:
                logger.info(f"{strategy_key} 波段阈值设为禁用(>=101)")
            return val
        
        return self._normalize_threshold_value(strategy_cfg.get('c_point_threshold', fallback), fallback)
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
                    logger.info(f"配置加载成功: {self.config_path}")
                try:
                    # 补齐缺失的股性阈值字段（向后兼容旧配置）
                    s1 = self._config_cache.get("strategy1", {})
                    s2 = self._config_cache.get("strategy2", {})
                    default_s1 = s1.get("c_point_threshold", 70)
                    default_s2 = s2.get("c_point_threshold", 20)
                    s1.setdefault("nature_thresholds", {})
                    s2.setdefault("nature_thresholds", {})
                    for nature in ["短线", "波段", "中长线"]:
                        s1["nature_thresholds"].setdefault(nature, default_s1)
                        s2["nature_thresholds"].setdefault(nature, default_s2)
                    self._config_cache["strategy1"] = s1
                    self._config_cache["strategy2"] = s2
                    # 补齐R点插件默认配置（向后兼容）
                    self._ensure_r_point_plugin_defaults()
                except Exception as compat_error:
                    logger.warning(f"补齐股性阈值时出错，使用原始配置: {compat_error}")
            else:
                # 如果配置文件不存在，使用默认配置
                default_thresholds = {"短线": 70, "波段": 70, "中长线": 70}
                self._config_cache = {
                    "strategy1": {
                        "c_point_threshold": 70,
                        "nature_thresholds": default_thresholds.copy(),
                        "description": "策略1 C点触发阈值（基于赔率分+胜率分+插件）"
                    },
                    "strategy2": {
                        "c_point_threshold": 20,
                        "nature_thresholds": {"短线": 20, "波段": 20, "中长线": 20},
                        "description": "策略2 C点触发阈值（基于MA+MACD+成交量+K线组合）"
                    },
                    "r_point_plugins": {
                        "pressure_stagnation": {
                            "distance_threshold_pct": 10.0,
                            "description": "临近压力位滞涨插件-股价距离压力线的百分比阈值"
                        },
                        "high_position_r": {
                            "gain_threshold_pct": 18.0,
                            "description": "高位发R插件-前20个交易日最低价到当前价格的涨幅阈值"
                        },
                        "high_stagnation_bearish": {
                            "gain_threshold_pct": 15.0,
                            "description": "高位滞涨+空头组合插件-X日最高价相对Y日最低价的涨幅阈值"
                        }
                    },
                    "market_type": "bull",
                    "market_type_description": "市场类型：bull=牛市, bear=熊市（人工判断）",
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self._save_config()
                logger.warning(f"配置文件不存在，已创建默认配置: {self.config_path}")
            
            # 兜底补齐R点插件默认配置
            self._ensure_r_point_plugin_defaults()
            
            return self._config_cache
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            # 返回默认配置
            return {
                "strategy1": {"c_point_threshold": 70, "nature_thresholds": {"短线": 70, "波段": 70, "中长线": 70}},
                "strategy2": {"c_point_threshold": 20, "nature_thresholds": {"短线": 20, "波段": 20, "中长线": 20}}
            }
    
    def _ensure_r_point_plugin_defaults(self):
        """补齐R点插件默认配置，保持向后兼容"""
        if self._config_cache is None:
            return
        
        r_cfg = self._config_cache.setdefault("r_point_plugins", {})
        
        pressure_cfg = r_cfg.setdefault("pressure_stagnation", {})
        pressure_cfg.setdefault("distance_threshold_pct", 10.0)
        pressure_cfg.setdefault("description", "临近压力位滞涨插件-股价距离压力线的百分比阈值")
        
        high_position_cfg = r_cfg.setdefault("high_position_r", {})
        high_position_cfg.setdefault("gain_threshold_pct", 18.0)
        high_position_cfg.setdefault("description", "高位发R插件-前20个交易日最低价到当前价格的涨幅阈值")
        
        high_stagnation_cfg = r_cfg.setdefault("high_stagnation_bearish", {})
        high_stagnation_cfg.setdefault("gain_threshold_pct", 15.0)
        high_stagnation_cfg.setdefault("description", "高位滞涨+空头组合插件-X日最高价相对Y日最低价的涨幅阈值")
    
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
    
    def _compute_market_type(self, as_of: Optional[Any] = None) -> str:
        """
        根据日期规则计算市场类型。

        重要：回测/历史分析时，应传入“当前正在计算的历史日期”（as_of），而不是使用机器当前日期。

        Args:
            as_of: 支持 datetime/date/字符串(YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)；为空则使用当前日期
        """
        try:
            if as_of is None:
                d = datetime.now().date()
            elif isinstance(as_of, datetime):
                d = as_of.date()
            elif isinstance(as_of, date):
                d = as_of
            else:
                # 兼容 'YYYY-MM-DD ...' 字符串
                s = str(as_of).strip()
                if not s:
                    d = datetime.now().date()
                else:
                    d = datetime.strptime(s.split(" ")[0], "%Y-%m-%d").date()
        except Exception:
            d = datetime.now().date()

        return 'bear' if d < MARKET_TYPE_CUTOFF else 'bull'

    def _get_market_type_rule_info(self) -> Dict[str, Any]:
        """返回市场类型自动判定规则说明"""
        return {
            "mode": "date_rule",
            "rule_text": "2025-02-05（不含）之前为熊市，含当天及之后为牛市",
            "cutoff_date": MARKET_TYPE_CUTOFF.isoformat()
        }

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置，附带自动判定的市场类型"""
        if self._config_cache is None:
            self._load_config()
        
        # 每次返回前补齐R点插件默认配置（兼容旧文件）
        self._ensure_r_point_plugin_defaults()

        # 在配置中强制写入自动判定结果与规则说明，供前端展示
        self._config_cache['market_type'] = self._compute_market_type()
        self._config_cache['market_type_rule'] = self._get_market_type_rule_info()
        self._config_cache['market_type_description'] = "市场类型由日期自动判定：2025-02-05（不含）前为熊市，含当天及之后为牛市"

        return self._config_cache
    
    def get_strategy1_threshold(self, stock_nature: Optional[str] = None) -> float:
        """获取策略1的C点触发阈值（支持股性）"""
        return self._get_nature_threshold('strategy1', stock_nature, 70.0)
    
    def get_strategy2_threshold(self, stock_nature: Optional[str] = None) -> float:
        """获取策略2的C点触发阈值（支持股性）"""
        return self._get_nature_threshold('strategy2', stock_nature, 20.0)
    
    def get_strategy_thresholds(self, strategy_key: str) -> Dict[str, float]:
        """获取某策略的股性阈值映射"""
        config = self.get_config()
        strategy_cfg = config.get(strategy_key, {}) if isinstance(config, dict) else {}
        thresholds = strategy_cfg.get('nature_thresholds') or {}
        result = {}
        for k, v in thresholds.items():
            val = self._normalize_threshold_value(v, None)
            if val is None:
                continue
            result[k] = val
        return result
    
    def get_market_type(self, as_of: Optional[Any] = None) -> str:
        """
        获取市场类型（自动判定）。

        - 实盘/当前：as_of=None（默认用机器当前日期）
        - 回测/历史：传入正在计算的K线日期 as_of=date/datetime/'YYYY-MM-DD'
        """
        return self._compute_market_type(as_of)
    
    def get_pressure_stagnation_distance_threshold(self) -> float:
        """获取临近压力位滞涨插件的距离阈值（百分比）"""
        config = self.get_config()
        return float(config.get('r_point_plugins', {}).get('pressure_stagnation', {}).get('distance_threshold_pct', 10.0))
    
    def get_high_position_gain_threshold(self) -> float:
        """获取高位发R插件的涨幅阈值（百分比）"""
        config = self.get_config()
        return float(config.get('r_point_plugins', {}).get('high_position_r', {}).get('gain_threshold_pct', 18.0))
    
    def get_high_stagnation_gain_threshold(self) -> float:
        """获取高位滞涨+空头组合插件的高低点涨幅阈值（百分比）"""
        config = self.get_config()
        return float(config.get('r_point_plugins', {}).get('high_stagnation_bearish', {}).get('gain_threshold_pct', 15.0))
    
    def update_config(self, strategy1_threshold: float = None, strategy2_threshold: float = None, market_type: str = None, 
                     pressure_distance_threshold: float = None, high_position_gain_threshold: float = None,
                     high_stagnation_gain_threshold: float = None,
                     strategy1_nature_thresholds: Dict[str, float] = None, strategy2_nature_thresholds: Dict[str, float] = None) -> Dict[str, Any]:
        """更新配置"""
        config = self.get_config()
        
        if strategy1_threshold is not None:
            config.setdefault('strategy1', {})
            config['strategy1']['c_point_threshold'] = strategy1_threshold
            logger.info(f"策略1阈值更新为: {strategy1_threshold}")
        
        if strategy2_threshold is not None:
            config.setdefault('strategy2', {})
            config['strategy2']['c_point_threshold'] = strategy2_threshold
            logger.info(f"策略2阈值更新为: {strategy2_threshold}")
        
        if strategy1_nature_thresholds:
            config.setdefault('strategy1', {})
            config['strategy1'].setdefault('nature_thresholds', {})
            for nature, value in strategy1_nature_thresholds.items():
                if value is None:
                    continue
                config['strategy1']['nature_thresholds'][nature] = value
                logger.info(f"策略1股性[{nature}]阈值更新为: {value}")
        
        if strategy2_nature_thresholds:
            config.setdefault('strategy2', {})
            config['strategy2'].setdefault('nature_thresholds', {})
            for nature, value in strategy2_nature_thresholds.items():
                if value is None:
                    continue
                config['strategy2']['nature_thresholds'][nature] = value
                logger.info(f"策略2股性[{nature}]阈值更新为: {value}")
        
        if market_type is not None:
            # 市场类型已由日期规则自动判定，忽略外部更新请求
            logger.info(f"市场类型更新请求已忽略，当前自动判定值为: {self._compute_market_type()}")
        
        # 确保r_point_plugins配置存在
        if 'r_point_plugins' not in config:
            config['r_point_plugins'] = {
                'pressure_stagnation': {},
                'high_position_r': {},
                'high_stagnation_bearish': {}
            }
        
        if pressure_distance_threshold is not None:
            if 'pressure_stagnation' not in config['r_point_plugins']:
                config['r_point_plugins']['pressure_stagnation'] = {}
            config['r_point_plugins']['pressure_stagnation']['distance_threshold_pct'] = pressure_distance_threshold
            logger.info(f"临近压力位滞涨-距离阈值更新为: {pressure_distance_threshold}%")
        
        if high_position_gain_threshold is not None:
            if 'high_position_r' not in config['r_point_plugins']:
                config['r_point_plugins']['high_position_r'] = {}
            config['r_point_plugins']['high_position_r']['gain_threshold_pct'] = high_position_gain_threshold
            logger.info(f"高位发R-涨幅阈值更新为: {high_position_gain_threshold}%")
        
        if high_stagnation_gain_threshold is not None:
            if 'high_stagnation_bearish' not in config['r_point_plugins']:
                config['r_point_plugins']['high_stagnation_bearish'] = {}
            config['r_point_plugins']['high_stagnation_bearish']['gain_threshold_pct'] = high_stagnation_gain_threshold
            logger.info(f"高位滞涨+空头组合-高低点涨幅阈值更新为: {high_stagnation_gain_threshold}%")
        
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

