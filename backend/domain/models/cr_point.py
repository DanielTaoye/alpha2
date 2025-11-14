"""CR点领域模型"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ABCComponents:
    """K线ABC组成部分"""
    a: float  # 上引线：最高价 - max(开盘价, 收盘价)
    b: float  # 实体：max(开盘价, 收盘价) - min(开盘价, 收盘价)
    c: float  # 下引线：min(开盘价, 收盘价) - 最低价
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'a': round(self.a, 4),
            'b': round(self.b, 4),
            'c': round(self.c, 4)
        }


@dataclass
class CRPoint:
    """CR点实体（买入C点和卖出R点）"""
    id: Optional[int] = None
    stock_code: str = ''
    stock_name: str = ''
    point_type: str = ''  # 'C' 或 'R'
    trigger_date: Optional[datetime] = None
    trigger_price: float = 0
    open_price: float = 0
    high_price: float = 0
    low_price: float = 0
    close_price: float = 0
    volume: int = 0
    a_value: float = 0  # 上引线
    b_value: float = 0  # 实体
    c_value: float = 0  # 下引线
    score: float = 0  # 策略得分
    strategy_name: str = ''  # 策略名称
    plugins: List[Dict[str, Any]] = field(default_factory=list)  # 触发的插件信息
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pointType': self.point_type,
            'triggerDate': self.trigger_date.strftime('%Y-%m-%d') if self.trigger_date else None,
            'triggerPrice': self.trigger_price,
            'openPrice': self.open_price,
            'highPrice': self.high_price,
            'lowPrice': self.low_price,
            'closePrice': self.close_price,
            'volume': self.volume,
            'aValue': self.a_value,
            'bValue': self.b_value,
            'cValue': self.c_value,
            'score': self.score,
            'strategyName': self.strategy_name,
            'plugins': self.plugins,  # 插件信息
            'createdAt': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

