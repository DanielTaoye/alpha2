"""流式微批分数查询控制器"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from application.services.streaming_score_service import get_streaming_service, get_master_db_connection
from domain.services.config_service import get_config_service
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_api_logger
import pymysql
import pymysql.cursors

logger = get_api_logger()


class StreamingScoreController:
    """流式微批分数查询控制器 - 快速查询数据库"""
    
    def __init__(self):
        self.streaming_service = get_streaming_service()
        self.config_service = get_config_service()
    
    def get_high_score_stocks(self):
        """
        获取高分股票列表（毫秒级查询）
        
        直接查询数据库的is_high_score字段，无需实时计算
        
        Returns:
            高分股票列表，按总分降序
        """
        try:
            data = request.get_json() or {}
            limit = data.get('limit', 100)
            date = data.get('date')  # 可选：指定日期，默认今天
            
            logger.info(f"收到请求: 获取高分股票列表 (limit={limit}, date={date})")
            
            # 从数据库快速查询
            stocks = self._query_high_score_stocks(limit, date)
            
            # 获取当前阈值
            strategy1_threshold = self.config_service.get_strategy1_threshold()
            strategy2_threshold = self.config_service.get_strategy2_threshold()
            
            # 获取服务统计信息
            stats = self.streaming_service.get_stats()
            
            response_data = {
                'stocks': stocks,
                'total': len(stocks),
                'thresholds': {
                    'strategy1': strategy1_threshold,
                    'strategy2': strategy2_threshold
                },
                'service_stats': stats
            }
            
            logger.info(f"查询完成: 找到 {len(stocks)} 只高分股票")
            return jsonify(ResponseBuilder.success(response_data, f"找到 {len(stocks)} 只高分股票"))
            
        except Exception as e:
            logger.error(f"查询高分股票失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def _query_high_score_stocks(self, limit: int, date: str = None) -> list:
        """从数据库快速查询高分股票（可以使用从库，只读）"""
        try:
            # 查询操作可以使用默认连接（可能是从库）
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                # SQL查询：直接从数据库读取，毫秒级
                if date:
                    sql = """
                        SELECT 
                            stock_code,
                            stock_name,
                            stock_nature as nature,
                            date,
                            strategy1_score,
                            strategy2_score,
                            total_score,
                            volume_type,
                            score_updated_at
                        FROM b_daily_chance
                        WHERE is_high_score = 1
                          AND date = %s
                          AND strategy1_score IS NOT NULL
                          AND strategy2_score IS NOT NULL
                        ORDER BY total_score DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (date, limit))
                else:
                    sql = """
                        SELECT 
                            stock_code,
                            stock_name,
                            stock_nature as nature,
                            date,
                            strategy1_score,
                            strategy2_score,
                            total_score,
                            volume_type,
                            score_updated_at
                        FROM b_daily_chance
                        WHERE is_high_score = 1
                          AND date = CURDATE()
                          AND strategy1_score IS NOT NULL
                          AND strategy2_score IS NOT NULL
                        ORDER BY total_score DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (limit,))
                
                results = cursor.fetchall()
                
                # 转换为前端需要的格式
                stocks = []
                for row in results:
                    stocks.append({
                        'stock_code': row['stock_code'],
                        'stock_name': row['stock_name'],
                        'nature': row['nature'] or '波段',
                        'table_name': f"basic_data_{row['stock_code'].lower()}",
                        'date': row['date'].strftime('%Y-%m-%d') if row['date'] else None,
                        'strategy1_score': float(row['strategy1_score']) if row['strategy1_score'] else 0,
                        'strategy2_score': float(row['strategy2_score']) if row['strategy2_score'] else 0,
                        'total_score': float(row['total_score']) if row['total_score'] else 0,
                        'strategy1_triggered': True,  # is_high_score=1 说明都已触发
                        'strategy2_triggered': True,
                        'max_score': max(
                            float(row['strategy1_score']) if row['strategy1_score'] else 0,
                            float(row['strategy2_score']) if row['strategy2_score'] else 0
                        ),
                        'volume_type': row['volume_type'] or '-',
                        'score_updated_at': row['score_updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row['score_updated_at'] else None
                    })
                
                return stocks
                
        except Exception as e:
            logger.error(f"数据库查询失败: {e}", exc_info=True)
            return []
    
    def get_service_status(self):
        """获取流式服务状态"""
        try:
            stats = self.streaming_service.get_stats()
            is_running = self.streaming_service._is_running
            
            return jsonify(ResponseBuilder.success({
                'is_running': is_running,
                'stats': stats
            }))
            
        except Exception as e:
            logger.error(f"获取服务状态失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def start_service(self):
        """手动启动流式服务"""
        try:
            self.streaming_service.start()
            return jsonify(ResponseBuilder.success(None, "流式服务已启动"))
        except Exception as e:
            logger.error(f"启动服务失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def stop_service(self):
        """手动停止流式服务"""
        try:
            self.streaming_service.stop()
            return jsonify(ResponseBuilder.success(None, "流式服务已停止"))
        except Exception as e:
            logger.error(f"停止服务失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
