"""CR点仓储接口"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.models.cr_point import CRPoint


class CRPointRepository(ABC):
    """CR点仓储接口"""
    
    @abstractmethod
    def save(self, cr_point: CRPoint) -> bool:
        """保存CR点"""
        pass
    
    @abstractmethod
    def find_by_stock_code(self, stock_code: str, point_type: Optional[str] = None) -> List[CRPoint]:
        """根据股票代码查询CR点"""
        pass
    
    @abstractmethod
    def find_by_date_range(self, stock_code: str, start_date: str, end_date: str) -> List[CRPoint]:
        """根据日期范围查询CR点"""
        pass
    
    @abstractmethod
    def delete_by_stock_and_date(self, stock_code: str, trigger_date: str) -> bool:
        """删除指定股票和日期的CR点"""
        pass

