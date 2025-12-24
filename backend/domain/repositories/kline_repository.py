"""K线数据仓储接口"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import datetime, date
from domain.models.kline import KLineData, PeriodInfo


class IKLineRepository(ABC):
    """K线数据仓储接口"""
    
    @abstractmethod
    def get_kline_data(
        self,
        table_name: str,
        period_type: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        limit: int = 2000
    ) -> List[KLineData]:
        """
        获取K线数据
        
        Args:
            table_name: 表名
            period_type: 周期类型
            start_date: 开始日期
            end_date: 结束日期（可选）
            limit: 数据条数限制
            
        Returns:
            K线数据列表
        """
        pass
    
    @abstractmethod
    def get_available_periods(self, table_name: str) -> List[PeriodInfo]:
        """
        获取可用的周期类型
        
        Args:
            table_name: 表名
            
        Returns:
            周期信息列表
        """
        pass
    
    @abstractmethod
    def get_latest_day_1min_data(self, table_name: str, target_date: Optional[date] = None) -> List[KLineData]:
        """
        获取最新一天的1分钟级别数据
        
        Args:
            table_name: 表名
            target_date: 目标日期，如果为None则获取最新交易日
            
        Returns:
            1分钟K线数据列表
        """
        pass
    
    @abstractmethod
    def get_recent_days_1min_data(self, table_name: str, days: int = 5) -> Dict[date, List[KLineData]]:
        """
        获取最近N个交易日的1分钟级别数据
        
        Args:
            table_name: 表名
            days: 获取最近多少个交易日，默认5天
            
        Returns:
            字典，key为日期，value为该日期的1分钟K线数据列表
        """
        pass

