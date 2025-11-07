"""股票分析控制器"""
from flask import jsonify, request
from application.services.analysis_service import AnalysisApplicationService
from infrastructure.external_apis.stock_analysis_repository_impl import StockAnalysisRepositoryImpl
from interfaces.dto.response import ResponseBuilder


class AnalysisController:
    """股票分析控制器"""
    
    def __init__(self):
        analysis_repository = StockAnalysisRepositoryImpl()
        self.analysis_service = AnalysisApplicationService(analysis_repository)
    
    def get_stock_analysis(self):
        """获取股票分析数据（益损比、压力线、支撑线）"""
        try:
            data = request.json
            stock_code = data.get('stock_code')
            
            analysis_data = self.analysis_service.get_stock_analysis(stock_code)
            
            # 总是返回成功，即使分析数据为空
            return jsonify(ResponseBuilder.success(analysis_data))
        
        except Exception as e:
            # 返回空数据而不是500错误
            empty_data = {
                '30min': {},
                'day': {},
                'week': {},
                'month': {}
            }
            return jsonify(ResponseBuilder.success(
                data=empty_data, 
                message=f'Analysis failed: {str(e)}'
            ))

