"""股票分析控制器"""
from flask import jsonify, request
from application.services.analysis_service import AnalysisApplicationService
from infrastructure.external_apis.stock_analysis_repository_impl import StockAnalysisRepositoryImpl
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_api_logger

logger = get_api_logger()


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
            
            logger.info(f"收到请求: 获取股票分析, 股票代码={stock_code}")
            analysis_data = self.analysis_service.get_stock_analysis(stock_code)
            
            # 记录返回的数据
            has_data = any(bool(v) for v in analysis_data.values())
            if has_data:
                logger.info(f"成功返回股票分析数据: {stock_code}")
            else:
                logger.warning(f"股票分析数据为空: {stock_code}")
            
            # 总是返回成功，即使分析数据为空
            return jsonify(ResponseBuilder.success(analysis_data))
        
        except Exception as e:
            logger.error(f"获取股票分析失败: 股票代码={stock_code}, 错误={str(e)}", exc_info=True)
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

