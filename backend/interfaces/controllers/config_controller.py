"""
配置管理控制器
"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger
from domain.services.config_service import get_config_service

logger = get_logger(__name__)


class ConfigController:
    """配置管理控制器"""
    
    def __init__(self):
        self.config_service = get_config_service()
    
    def get_config(self):
        """获取当前配置"""
        try:
            config = self.config_service.get_config()
            return jsonify(ResponseBuilder.success(config, '配置获取成功')), 200
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return jsonify(ResponseBuilder.error(f'获取配置失败: {str(e)}')), 500
    
    def update_config(self):
        """更新配置"""
        try:
            data = request.get_json()
            
            strategy1_threshold = data.get('strategy1_threshold')
            strategy2_threshold = data.get('strategy2_threshold')
            market_type = data.get('market_type')
            pressure_distance_threshold = data.get('pressure_distance_threshold')
            high_position_gain_threshold = data.get('high_position_gain_threshold')
            
            # 参数验证
            if strategy1_threshold is not None:
                try:
                    strategy1_threshold = float(strategy1_threshold)
                    if strategy1_threshold < 0 or strategy1_threshold > 100:
                        return jsonify(ResponseBuilder.error('策略1阈值必须在0-100之间')), 400
                except (ValueError, TypeError):
                    return jsonify(ResponseBuilder.error('策略1阈值必须是数字')), 400
            
            if strategy2_threshold is not None:
                try:
                    strategy2_threshold = float(strategy2_threshold)
                    if strategy2_threshold < 0 or strategy2_threshold > 100:
                        return jsonify(ResponseBuilder.error('策略2阈值必须在0-100之间')), 400
                except (ValueError, TypeError):
                    return jsonify(ResponseBuilder.error('策略2阈值必须是数字')), 400
            
            if market_type is not None:
                if market_type not in ['bull', 'bear']:
                    return jsonify(ResponseBuilder.error('市场类型必须是 bull 或 bear')), 400
            
            if pressure_distance_threshold is not None:
                try:
                    pressure_distance_threshold = float(pressure_distance_threshold)
                    if pressure_distance_threshold < 0 or pressure_distance_threshold > 100:
                        return jsonify(ResponseBuilder.error('临近压力位滞涨-距离阈值必须在0-100之间')), 400
                except (ValueError, TypeError):
                    return jsonify(ResponseBuilder.error('临近压力位滞涨-距离阈值必须是数字')), 400
            
            if high_position_gain_threshold is not None:
                try:
                    high_position_gain_threshold = float(high_position_gain_threshold)
                    if high_position_gain_threshold < 0 or high_position_gain_threshold > 100:
                        return jsonify(ResponseBuilder.error('高位发R-涨幅阈值必须在0-100之间')), 400
                except (ValueError, TypeError):
                    return jsonify(ResponseBuilder.error('高位发R-涨幅阈值必须是数字')), 400
            
            # 更新配置
            updated_config = self.config_service.update_config(
                strategy1_threshold=strategy1_threshold,
                strategy2_threshold=strategy2_threshold,
                market_type=market_type,
                pressure_distance_threshold=pressure_distance_threshold,
                high_position_gain_threshold=high_position_gain_threshold
            )
            
            # 构建更新信息
            update_info_parts = []
            if strategy1_threshold is not None:
                update_info_parts.append(f'策略1:{strategy1_threshold}')
            if strategy2_threshold is not None:
                update_info_parts.append(f'策略2:{strategy2_threshold}')
            if market_type is not None:
                update_info_parts.append(f'市场类型:{market_type}')
            if pressure_distance_threshold is not None:
                update_info_parts.append(f'压力位距离阈值:{pressure_distance_threshold}%')
            if high_position_gain_threshold is not None:
                update_info_parts.append(f'高位发R涨幅阈值:{high_position_gain_threshold}%')
            
            update_info = ', '.join(update_info_parts) if update_info_parts else '未改变'
            
            logger.info(f"配置更新成功: {update_info}")
            
            return jsonify(ResponseBuilder.success(
                updated_config, 
                f'配置更新成功 ({update_info})'
            )), 200
            
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return jsonify(ResponseBuilder.error(f'更新配置失败: {str(e)}')), 500
    
    def reload_config(self):
        """重新加载配置"""
        try:
            self.config_service.reload_config()
            config = self.config_service.get_config()
            return jsonify(ResponseBuilder.success(config, '配置重新加载成功')), 200
        except Exception as e:
            logger.error(f"重新加载配置失败: {e}")
            return jsonify(ResponseBuilder.error(f'重新加载配置失败: {str(e)}')), 500

