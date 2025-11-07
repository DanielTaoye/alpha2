"""K线数据控制器"""
from flask import jsonify, request
from application.services.kline_service import KLineApplicationService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
from interfaces.dto.response import ResponseBuilder


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
            
            periods = self.kline_service.get_available_periods(table_name)
            return jsonify(ResponseBuilder.success(periods))
        
        except Exception as e:
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def get_kline_data(self):
        """获取K线数据"""
        try:
            data = request.json
            table_name = data.get('table_name')
            period_type = data.get('period_type', 'day')
            
            kline_data = self.kline_service.get_kline_data(table_name, period_type)
            return jsonify(ResponseBuilder.success(kline_data))
        
        except Exception as e:
            return jsonify(ResponseBuilder.error(str(e))), 500

