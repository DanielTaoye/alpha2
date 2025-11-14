"""K线数据控制器"""
from flask import jsonify, request
from application.services.kline_service import KLineApplicationService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_api_logger

logger = get_api_logger()


class KLineController:
    """K线数据控制器"""
    
    def __init__(self):
        kline_repository = KLineRepositoryImpl()
        self.kline_service = KLineApplicationService(kline_repository)
    
    def get_available_periods(self):
        """获取股票可用的周期类型"""
        try:
            data = request.json
            table_name = data.get('table_name')
            
            logger.info(f"收到请求: 获取可用周期, 表名={table_name}")
            periods = self.kline_service.get_available_periods(table_name)
            logger.info(f"成功返回可用周期: {list(periods.keys())}")
            return jsonify(ResponseBuilder.success(periods))
        
        except Exception as e:
            logger.error(f"获取可用周期失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def get_kline_data(self):
        """获取K线数据及技术指标"""
        try:
            data = request.json
            table_name = data.get('table_name')
            period_type = data.get('period_type', 'day')
            
            logger.info(f"收到请求: 获取K线数据, 表名={table_name}, 周期={period_type}")
            result = self.kline_service.get_kline_data(table_name, period_type)
            
            # result现在是一个字典，包含kline_data和macd
            kline_count = len(result.get('kline_data', []))
            logger.info(f"成功返回K线数据，共{kline_count}条记录，已附带MACD指标")
            return jsonify(ResponseBuilder.success(result))
        
        except Exception as e:
            logger.error(f"获取K线数据失败: 表名={table_name}, 周期={period_type}, 错误={str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500

