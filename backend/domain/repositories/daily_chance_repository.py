"""每日机会仓储接口"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.models.daily_chance import DailyChance


class IDailyChanceRepository(ABC):
    """每日机会仓储接口"""
    
    @abstractmethod
    def save(self, daily_chance: DailyChance) -> bool:
        """保存每日机会数据"""
        pass
    
    @abstractmethod
    def save_batch(self, daily_chances: List[DailyChance]) -> int:
        """批量保存每日机会数据"""
        pass
    
    @abstractmethod
    def find_by_stock_and_date(self, stock_code: str, date: str) -> Optional[DailyChance]:
        """根据股票代码和日期查询单条数据"""
        pass
    
    @abstractmethod
    def find_by_stock_code(self, stock_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[DailyChance]:
        """根据股票代码查询"""
        pass
    
    @abstractmethod
    def find_by_date(self, date: str) -> List[DailyChance]:
        """根据日期查询"""
        pass
    
    @abstractmethod
    def find_latest_date(self, stock_code: str) -> Optional[str]:
        """获取股票最新的数据日期"""
        pass
    
    @abstractmethod
    def update_volume_type(self, stock_code: str, date: str, volume_type: str) -> bool:
        """更新成交量类型"""
        pass
    
    @abstractmethod
    def update_volume_type_batch(self, updates: List[tuple]) -> int:
        """批量更新成交量类型"""
        pass
    
    @abstractmethod
    def update_bullish_pattern_batch(self, updates: List[tuple]) -> int:
        """批量更新多头组合"""
        pass
    
    @abstractmethod
    def update_bearish_pattern_batch(self, updates: List[tuple]) -> int:
        """批量更新空头组合"""
        pass

