"""最新一天CR点控制器"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from application.services.latest_cr_point_service import LatestCRPointService
from application.services.kline_service import KLineApplicationService
from application.services.daily_chance_service import DailyChanceService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class LatestCRPointController:
    """最新一天CR点控制器"""
    
    def __init__(self):
        # 初始化依赖服务
        kline_repo = KLineRepositoryImpl()
        self.kline_service = KLineApplicationService(kline_repo)
        
        daily_chance_repo = DailyChanceRepositoryImpl()
        api_client = DailyChanceApiClient()
        self.daily_chance_service = DailyChanceService(daily_chance_repo)
        self.daily_chance_service.api_client = api_client
        
        self.latest_cr_service = LatestCRPointService(
            self.kline_service,
            self.daily_chance_service
        )
    
    def get_latest_cr_points(self):
        """获取最新一天的CR点"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            table_name = data.get('tableName')
            stock_nature = data.get('stockNature') or data.get('stock_nature')
            
            if not stock_code or not table_name:
                return jsonify(ResponseBuilder.error("缺少参数: stockCode 或 tableName", code=400))
            
            logger.info(f"收到请求: 获取最新CR点, 股票={stock_code}, 表名={table_name}")
            
            # 可选：前端可以传入已经计算好的预测成交量和成交量类型
            predicted_volume = data.get('predictedVolume')
            volume_type = data.get('volumeType')
            
            # 计算最新一天的CR点
            result = self.latest_cr_service.calculate_latest_cr_points(
                stock_code,
                table_name,
                predicted_volume,
                volume_type,
                stock_nature
            )
            
            if result.get('success'):
                return jsonify(ResponseBuilder.success(result, "计算成功"))
            else:
                return jsonify(ResponseBuilder.error(result.get('message', '计算失败')))
            
        except Exception as e:
            logger.error(f"获取最新CR点失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"获取失败: {str(e)}"))

