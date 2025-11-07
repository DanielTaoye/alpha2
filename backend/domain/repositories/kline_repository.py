"""K线数据仓储接口"""
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime
from domain.models.kline import KLineData, PeriodInfo


class IKLineRepository(ABC):
    """K线数据仓储接口"""
    
    @abstractmethod
    def get_kline_data(self, table_name: str, period_type: str, 
                      start_date: datetime, limit: int = 2000) -> List[KLineData]:
        """
        获取K线数据
        
        Args:
            table_name: 表名
            period_type: 周期类型
            start_date: 开始日期
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

