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
    
    def get_latest_day_kline(self):
        """获取最新一天的K线数据（从1分钟数据聚合）"""
        try:
            data = request.json
            table_name = data.get('table_name')
            
            logger.info(f"收到请求: 获取最新一天K线数据, 表名={table_name}")
            result = self.kline_service.get_latest_day_kline(table_name)
            
            if result.get('kline_data'):
                logger.info(f"成功返回最新K线数据: 日期={result.get('trade_date')}")
            else:
                logger.warning(f"未找到最新K线数据: {result.get('message')}")
            
            return jsonify(ResponseBuilder.success(result))
        
        except Exception as e:
            logger.error(f"获取最新K线数据失败: 表名={table_name}, 错误={str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def predict_volume(self):
        """预测当天的成交量"""
        try:
            data = request.json
            table_name = data.get('table_name')
            
            logger.info(f"收到请求: 预测成交量, 表名={table_name}")
            result = self.kline_service.predict_today_volume(table_name)
            
            if result.get('predicted_volume'):
                logger.info(f"成功预测成交量: 当前={result.get('current_volume'):.2f}, 预测={result.get('predicted_volume'):.2f}")
            else:
                logger.warning(f"无法预测成交量: {result.get('message')}")
            
            return jsonify(ResponseBuilder.success(result))
        
        except Exception as e:
            logger.error(f"预测成交量失败: 表名={table_name}, 错误={str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500

    def predict_volume_type(self):
        """基于预测成交量实时计算成交量类型"""
        try:
            from domain.services.volume_type_service import VolumeTypeService
            
            data = request.json
            table_name = data.get('table_name')
            predicted_volume = data.get('predicted_volume')
            
            if not table_name:
                return jsonify(ResponseBuilder.error("缺少参数: table_name")), 400
            
            if not predicted_volume:
                return jsonify(ResponseBuilder.error("缺少参数: predicted_volume")), 400
            
            logger.info(f"收到请求: 实时计算成交量类型, 表名={table_name}, 预测成交量={predicted_volume}")
            
            # 🔥 实时计算成交量类型
            volume_type = VolumeTypeService.calculate_volume_type_with_predicted(
                table_name=table_name,
                predicted_volume=float(predicted_volume)
            )
            
            if volume_type:
                logger.info(f"✅ 实时计算成交量类型: {volume_type}")
            else:
                logger.warning(f"⚠️ 未匹配任何成交量类型")
                volume_type = ''  # 返回空字符串而不是None
            
            result = {
                'volume_type': volume_type,
                'predicted_volume': predicted_volume
            }
            
            return jsonify(ResponseBuilder.success(result))
        
        except Exception as e:
            logger.error(f"计算成交量类型失败: 表名={table_name}, 错误={str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def _extract_stock_code_from_table(self, table_name: str) -> str:
        """
        从表名提取股票代码
        支持两种格式:
        1. basic_data_sz300188 -> SZ300188
        2. sz_300188_kline -> SZ300188
        """
        # 移除前缀 basic_data_
        if table_name.startswith('basic_data_'):
            table_name = table_name[11:]  # 移除 "basic_data_"
        
        # 移除后缀 _kline
        if table_name.endswith('_kline'):
            table_name = table_name[:-6]
        
        # 现在 table_name 应该是 sz300188 或 sz_300188 格式
        # 尝试按 _ 分割
        if '_' in table_name:
            # sz_300188 -> SZ300188
            parts = table_name.split('_')
            if len(parts) >= 2:
                market = parts[0].upper()  # sz -> SZ 或 sh -> SH
                code = parts[1]  # 300188
                return f"{market}{code}"
        else:
            # sz300188 -> SZ300188
            # 前2个字符是市场代码，后面是股票代码
            if len(table_name) >= 3:
                market = table_name[:2].upper()  # sz -> SZ 或 sh -> SH
                code = table_name[2:]  # 300188
                return f"{market}{code}"
        
        return table_name.upper()

