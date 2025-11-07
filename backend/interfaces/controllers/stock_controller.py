"""股票控制器"""
from flask import jsonify
from application.services.stock_service import StockApplicationService
from interfaces.dto.response import ResponseBuilder


class StockController:
    """股票控制器"""
    
    def __init__(self):
        self.stock_service = StockApplicationService()
    
    def get_stock_groups(self):
        """获取股票分组信息"""
        try:
            groups = self.stock_service.get_all_stock_groups()
            return jsonify(ResponseBuilder.success(groups))
        except Exception as e:
            return jsonify(ResponseBuilder.error(str(e))), 500

