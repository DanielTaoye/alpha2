"""股票控制器"""
from flask import request, jsonify
from application.services.stock_service import StockApplicationService
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_api_logger

logger = get_api_logger()


class StockController:
    """股票控制器"""
    
    def __init__(self):
        self.stock_service = StockApplicationService()
    
    def get_stock_groups(self):
        """获取股票分组信息（59支代表性股票）"""
        try:
            logger.info("收到请求: 获取股票分组信息")
            groups = self.stock_service.get_all_stock_groups()
            logger.info(f"成功返回股票分组，共{len(groups)}个分组")
            return jsonify(ResponseBuilder.success(groups))
        except Exception as e:
            logger.error(f"获取股票分组失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def search_stocks(self):
        """搜索全部股票（从 all_stock 表）"""
        try:
            keyword = request.args.get('keyword', '').strip()
            limit = int(request.args.get('limit', 100))
            
            if not keyword:
                return jsonify(ResponseBuilder.error("搜索关键词不能为空", code=400))
            
            logger.info(f"收到请求: 搜索股票, 关键词='{keyword}', limit={limit}")
            
            stocks = self.stock_service.search_stocks(keyword, limit)
            
            logger.info(f"搜索完成: 找到 {len(stocks)} 只股票")
            return jsonify(ResponseBuilder.success(stocks, f"找到 {len(stocks)} 只股票"))
            
        except Exception as e:
            logger.error(f"搜索股票失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500

