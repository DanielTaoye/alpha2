"""股票分析数据仓储实现"""
from typing import Dict
from domain.repositories.stock_analysis_repository import IStockAnalysisRepository
from domain.models.kline import StockAnalysis
from infrastructure.external_apis.stock_analysis_api import StockAnalysisApiClient


class StockAnalysisRepositoryImpl(IStockAnalysisRepository):
    """股票分析数据仓储实现（通过外部API）"""
    
    def __init__(self):
        self.api_client = StockAnalysisApiClient()
    
    def get_stock_analysis(self, stock_code: str) -> Dict[str, StockAnalysis]:
        """获取股票分析数据"""
        # 调用API获取数据
        api_result = self.api_client.get_stock_analysis(stock_code)
        
        # 转换为领域模型
        result = {}
        for period, data in api_result.items():
            if data:
                result[period] = StockAnalysis(
                    win_lose_ratio=data.get('winLoseRatio', 0),
                    support_price=data.get('supportPrice', 0),
                    pressure_price=data.get('pressurePrice', 0)
                )
            else:
                result[period] = StockAnalysis()
        
        return result

