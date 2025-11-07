"""股票控制器"""
from flask import jsonify
from application.services.stock_service import StockApplicationService
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_api_logger

logger = get_api_logger()


class StockController:
    """股票控制器"""
    
    def __init__(self):
        self.stock_service = StockApplicationService()
    
    def get_stock_groups(self):
        """获取股票分组信息"""
        try:
            logger.info("收到请求: 获取股票分组信息")
            groups = self.stock_service.get_all_stock_groups()
            logger.info(f"成功返回股票分组，共{len(groups)}个分组")
            return jsonify(ResponseBuilder.success(groups))
        except Exception as e:
            logger.error(f"获取股票分组失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500

