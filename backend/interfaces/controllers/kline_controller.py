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
        """从数据库获取最新的成交量类型（直接读取b_daily_chance表）"""
        try:
            import pymysql.cursors
            from infrastructure.persistence.database import DatabaseConnection
            
            data = request.json
            table_name = data.get('table_name')
            predicted_volume = data.get('predicted_volume')
            
            if not table_name:
                return jsonify(ResponseBuilder.error("缺少参数: table_name")), 400
            
            # 从table_name提取股票代码 (例如: sz_300188_kline -> SZ300188)
            stock_code = self._extract_stock_code_from_table(table_name)
            
            logger.info(f"收到请求: 获取成交量类型, 表名={table_name}, 转换后股票代码={stock_code}")
            
            # 直接从b_daily_chance表读取最新的成交量类型
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                # 查询最近5天的数据，取最新的成交量类型
                query = """
                    SELECT volume_type, date, stock_code
                    FROM b_daily_chance
                    WHERE stock_code = %s
                    ORDER BY date DESC
                    LIMIT 5
                """
                logger.info(f"🔍 执行SQL查询: stock_code={stock_code}")
                cursor.execute(query, (stock_code,))
                results = cursor.fetchall()
                
                logger.info(f"🔍 查询结果数量: {len(results)}条")
                if results:
                    for i, r in enumerate(results):
                        logger.info(f"  [{i}] 日期={r['date']}, stock_code={r['stock_code']}, volume_type={r['volume_type']}")
                
                volume_type = None
                if results and results[0]['volume_type']:
                    volume_type = results[0]['volume_type']
                    latest_date = results[0]['date']
                    logger.info(f"✅ 从数据库读取成交量类型: {volume_type}, 日期: {latest_date}")
                else:
                    if not results:
                        logger.warning(f"⚠️ 未找到任何数据: stock_code={stock_code}")
                    else:
                        logger.warning(f"⚠️ 找到数据但volume_type为空: stock_code={stock_code}, 日期={results[0]['date']}")
            
            result = {
                'volume_type': volume_type,
                'predicted_volume': predicted_volume
            }
            
            return jsonify(ResponseBuilder.success(result))
        
        except Exception as e:
            logger.error(f"获取成交量类型失败: 表名={table_name}, 错误={str(e)}", exc_info=True)
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

