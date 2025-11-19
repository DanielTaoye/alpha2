"""回测控制器"""
from flask import request, jsonify
from typing import Dict, Any
from application.services.backtest_service import BacktestService
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class BacktestController:
    """回测控制器"""
    
    def __init__(self):
        self.backtest_service = BacktestService()
    
    def run_backtest(self):
        """
        执行回测
        
        请求参数:
            stock_code: 股票代码
            table_name: K线数据表名
            c_points: C点列表
            r_points: R点列表
        
        返回:
            回测结果
        """
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            table_name = data.get('tableName')
            c_points = data.get('cPoints', [])
            r_points = data.get('rPoints', [])
            
            if not stock_code:
                return jsonify(ResponseBuilder.error('股票代码不能为空')), 400
            
            if not table_name:
                return jsonify(ResponseBuilder.error('表名不能为空')), 400
            
            logger.info(f"开始执行回测: {stock_code} 表:{table_name}")
            
            # 执行回测
            result = self.backtest_service.calculate_backtest(
                stock_code, table_name, c_points, r_points
            )
            
            if result['success']:
                return jsonify(ResponseBuilder.success(
                    result, 
                    f'回测完成，共{result["summary"].get("total_trades", 0)}笔交易'
                )), 200
            else:
                # 返回400而不是500，因为这是业务错误不是服务器错误
                return jsonify(ResponseBuilder.error(result.get('message', '回测失败'))), 400
            
        except Exception as e:
            logger.error(f"执行回测失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f'执行回测失败: {str(e)}')), 500

