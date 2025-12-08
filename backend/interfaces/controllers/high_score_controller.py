"""高分股票扫描控制器"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from application.services.high_score_service import get_high_score_service
from domain.services.config_service import get_config_service
from infrastructure.logging.logger import get_api_logger

logger = get_api_logger()


class HighScoreController:
    """高分股票扫描控制器"""
    
    def __init__(self):
        self.high_score_service = get_high_score_service()
        self.config_service = get_config_service()
    
    def scan_high_score_stocks(self):
        """
        扫描高分股票
        
        请求体（可选）:
        {
            "strategy1_threshold": 75,  // 策略1阈值，默认从配置读取
            "strategy2_threshold": 85,  // 策略2阈值，默认从配置读取
            "use_cache": true,          // 是否使用缓存，默认true
            "max_workers": 50           // 并行线程数，默认50（I/O密集型，可设置50-100）
        }
        
        返回:
        {
            "code": 200,
            "data": {
                "stocks": [...],        // 高分股票列表
                "total": 10,            // 高分股票总数
                "scan_time": "...",     // 扫描时间
                "thresholds": {...}     // 使用的阈值
            }
        }
        """
        try:
            data = request.get_json() or {}
            
            # 获取参数
            strategy1_threshold = data.get('strategy1_threshold')
            strategy2_threshold = data.get('strategy2_threshold')
            use_cache = data.get('use_cache', True)
            max_workers = data.get('max_workers', 50)  # 默认50线程（I/O密集型，可以较多）
            
            # 限制最大线程数，避免过多
            max_workers = min(max_workers, 100)  # 最多100线程
            
            # 如果未提供阈值，从配置读取
            if strategy1_threshold is None:
                strategy1_threshold = self.config_service.get_strategy1_threshold()
            if strategy2_threshold is None:
                strategy2_threshold = self.config_service.get_strategy2_threshold()
            
            logger.info(f"收到请求: 扫描高分股票 (策略1≥{strategy1_threshold}, 策略2≥{strategy2_threshold}, 缓存={use_cache})")
            
            # 执行扫描
            result = self.high_score_service.scan_high_score_stocks(
                strategy1_threshold=strategy1_threshold,
                strategy2_threshold=strategy2_threshold,
                max_workers=max_workers,
                use_cache=use_cache
            )
            
            if result.get('success'):
                stocks = result.get('data', [])
                response_data = {
                    'stocks': stocks,
                    'total': len(stocks),
                    'scan_time': result.get('scan_time'),
                    'from_cache': result.get('from_cache', False),
                    'total_scanned': result.get('total_scanned', 0),
                    'elapsed_seconds': result.get('elapsed_seconds', 0),
                    'thresholds': {
                        'strategy1': strategy1_threshold,
                        'strategy2': strategy2_threshold
                    }
                }
                
                logger.info(f"扫描完成: 共 {len(stocks)} 只高分股票")
                return jsonify(ResponseBuilder.success(response_data, f"找到 {len(stocks)} 只高分股票"))
            else:
                return jsonify(ResponseBuilder.error(result.get('message', '扫描失败')))
            
        except Exception as e:
            logger.error(f"扫描高分股票失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def get_thresholds(self):
        """
        获取当前阈值配置
        
        返回:
        {
            "code": 200,
            "data": {
                "strategy1_threshold": 75,
                "strategy2_threshold": 85
            }
        }
        """
        try:
            strategy1_threshold = self.config_service.get_strategy1_threshold()
            strategy2_threshold = self.config_service.get_strategy2_threshold()
            
            return jsonify(ResponseBuilder.success({
                'strategy1_threshold': strategy1_threshold,
                'strategy2_threshold': strategy2_threshold
            }))
            
        except Exception as e:
            logger.error(f"获取阈值配置失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
    
    def clear_cache(self):
        """清空扫描缓存"""
        try:
            self.high_score_service.clear_cache()
            logger.info("高分股票扫描缓存已清空")
            return jsonify(ResponseBuilder.success(None, "缓存已清空"))
        except Exception as e:
            logger.error(f"清空缓存失败: {str(e)}", exc_info=True)
            return jsonify(ResponseBuilder.error(str(e))), 500
