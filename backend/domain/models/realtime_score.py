"""实时分数领域模型"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RealtimeScore:
    """实时分数实体（流式微批计算结果）"""
    stock_code: str
    stock_name: str
    date: datetime
    strategy1_score: float
    strategy2_score: float
    total_score: float
    is_high_score: bool
    score_updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,
            'strategy1Score': self.strategy1_score,
            'strategy2Score': self.strategy2_score,
            'totalScore': self.total_score,
            'isHighScore': self.is_high_score,
            'scoreUpdatedAt': self.score_updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.score_updated_at else None
        }
