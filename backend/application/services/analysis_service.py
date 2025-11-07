"""股票分析应用服务"""
from typing import Dict
from domain.repositories.stock_analysis_repository import IStockAnalysisRepository


class AnalysisApplicationService:
    """股票分析应用服务"""
    
    def __init__(self, analysis_repository: IStockAnalysisRepository):
        self.analysis_repository = analysis_repository
    
    def get_stock_analysis(self, stock_code: str) -> Dict[str, Dict]:
        """
        获取股票分析数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            各周期的分析数据字典
        """
        analysis_dict = self.analysis_repository.get_stock_analysis(stock_code)
        
        # 转换为字典格式
        result = {}
        for period, analysis in analysis_dict.items():
            result[period] = analysis.to_dict()
        
        return result

