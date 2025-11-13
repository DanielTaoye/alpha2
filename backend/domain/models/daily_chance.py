"""每日机会领域模型"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DailyChance:
    """每日机会实体"""
    id: Optional[int] = None
    stock_code: str = ''  # 股票代码
    stock_name: str = ''  # 股票名称
    stock_nature: str = ''  # 股性（波段、短线、中长线）
    date: Optional[datetime] = None  # 日期
    chance: float = 0.0  # 机会概率
    day_win_ratio_score: float = 0.0  # 日线赔率得分
    week_win_ratio_score: float = 0.0  # 周线赔率得分
    total_win_ratio_score: float = 0.0  # 赔率总分
    support_price: Optional[float] = None  # 支撑价格
    pressure_price: Optional[float] = None  # 压力价格
    volume_type: Optional[str] = None  # 成交量类型(A/B/C/D/E/F/G/H/X/Y/Z)
    bullish_pattern: Optional[str] = None  # 多头组合
    created_at: Optional[datetime] = None  # 创建时间
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'stockNature': self.stock_nature,
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,
            'chance': self.chance,
            'dayWinRatioScore': self.day_win_ratio_score,
            'weekWinRatioScore': self.week_win_ratio_score,
            'totalWinRatioScore': self.total_win_ratio_score,
            'supportPrice': self.support_price,
            'pressurePrice': self.pressure_price,
            'volumeType': self.volume_type,
            'bullishPattern': self.bullish_pattern,
            'createdAt': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

