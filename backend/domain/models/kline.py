"""K线数据领域模型"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class KLineData:
    """K线数据实体"""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    liangbi: float
    weibi: float
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'time': self.time.strftime('%Y-%m-%d %H:%M:%S'),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'liangbi': self.liangbi,
            'weibi': self.weibi
        }


@dataclass
class PeriodInfo:
    """周期信息值对象"""
    period_type: str
    count: int


@dataclass
class StockAnalysis:
    """股票分析数据实体"""
    win_lose_ratio: float = 0
    support_price: float = 0
    pressure_price: float = 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'winLoseRatio': self.win_lose_ratio,
            'supportPrice': self.support_price,
            'pressurePrice': self.pressure_price
        }

