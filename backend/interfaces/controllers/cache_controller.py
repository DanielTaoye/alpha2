"""缓存管理控制器"""
from flask import request, jsonify
from infrastructure.logging.logger import get_logger
from application.services.cr_cache_manager import get_cr_cache_manager

logger = get_logger(__name__)


class CacheController:
    """缓存管理控制器"""
    
    def __init__(self):
        self.cache_manager = get_cr_cache_manager()
    
    def get_cache_info(self):
        """获取缓存信息"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode') if data else None
            
            info = self.cache_manager.get_cache_info(stock_code)
            
            return jsonify({
                'code': 200,
                'data': info,
                'message': '获取缓存信息成功'
            })
            
        except Exception as e:
            logger.error(f"获取缓存信息失败: {e}", exc_info=True)
            return jsonify({
                'code': 500,
                'message': f'获取缓存信息失败: {str(e)}'
            }), 500
    
    def update_cache(self):
        """手动更新缓存"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            
            if not stock_code:
                return jsonify({
                    'code': 400,
                    'message': '缺少参数：stockCode'
                }), 400
            
            logger.info(f"手动更新缓存: {stock_code}")
            self.cache_manager.update_stock_cache(stock_code)
            
            return jsonify({
                'code': 200,
                'message': f'缓存更新成功: {stock_code}'
            })
            
        except Exception as e:
            logger.error(f"更新缓存失败: {e}", exc_info=True)
            return jsonify({
                'code': 500,
                'message': f'更新缓存失败: {str(e)}'
            }), 500
    
    def init_cache(self):
        """初始化缓存"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            days = data.get('days', 30)
            
            if not stock_code:
                return jsonify({
                    'code': 400,
                    'message': '缺少参数：stockCode'
                }), 400
            
            logger.info(f"初始化缓存: {stock_code}, days={days}")
            self.cache_manager.init_stock_cache(stock_code, days)
            
            return jsonify({
                'code': 200,
                'message': f'缓存初始化成功: {stock_code}'
            })
            
        except Exception as e:
            logger.error(f"初始化缓存失败: {e}", exc_info=True)
            return jsonify({
                'code': 500,
                'message': f'初始化缓存失败: {str(e)}'
            }), 500
    
    def clear_cache(self):
        """清空所有缓存"""
        try:
            logger.info("清空所有缓存")
            self.cache_manager.clear_all_cache()
            
            return jsonify({
                'code': 200,
                'message': '所有缓存已清空'
            })
            
        except Exception as e:
            logger.error(f"清空缓存失败: {e}", exc_info=True)
            return jsonify({
                'code': 500,
                'message': f'清空缓存失败: {str(e)}'
            }), 500

