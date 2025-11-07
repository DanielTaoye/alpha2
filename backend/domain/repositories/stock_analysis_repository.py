"""股票分析数据仓储接口"""
from abc import ABC, abstractmethod
from typing import Dict
from domain.models.kline import StockAnalysis


class IStockAnalysisRepository(ABC):
    """股票分析数据仓储接口"""
    
    @abstractmethod
    def get_stock_analysis(self, stock_code: str) -> Dict[str, StockAnalysis]:
        """
        获取股票分析数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            各周期的分析数据字典
        """
        pass

