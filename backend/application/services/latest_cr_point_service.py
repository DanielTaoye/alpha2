"""最新一天CR点计算服务"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger
from domain.services.cr_strategy_service import CRStrategyService
from domain.services.strategy2_service import Strategy2Service
from domain.services.r_point_plugin_service import RPointPluginService

logger = get_logger(__name__)


class LatestCRPointService:
    """最新一天CR点计算服务"""
    
    def __init__(self, kline_service, daily_chance_service):
        self.kline_service = kline_service
        self.daily_chance_service = daily_chance_service
        # 延迟初始化这些服务，避免启动时连接问题
        self._cr_strategy_service = None
        self._strategy2_service = None
        self._r_point_service = None
    
    @property
    def cr_strategy_service(self):
        if self._cr_strategy_service is None:
            self._cr_strategy_service = CRStrategyService()
        return self._cr_strategy_service
    
    @property
    def strategy2_service(self):
        if self._strategy2_service is None:
            self._strategy2_service = Strategy2Service()
        return self._strategy2_service
    
    @property
    def r_point_service(self):
        if self._r_point_service is None:
            self._r_point_service = RPointPluginService()
        return self._r_point_service
    
    def calculate_latest_cr_points(
        self, 
        stock_code: str, 
        table_name: str,
        predicted_volume: Optional[float] = None,
        volume_type: Optional[str] = None
    ) -> Dict:
        """
        计算最新一天的CR点
        
        Args:
            stock_code: 股票代码
            table_name: 表名
            predicted_volume: 预测成交量（可选，如果不提供则自动获取）
            volume_type: 成交量类型（可选，如果不提供则自动计算）
            
        Returns:
            包含C点、R点信息的字典
        """
        try:
            logger.info(f"开始计算最新一天CR点: {stock_code}")
            
            # 1. 获取最新一天的K线数据
            latest_kline_result = self.kline_service.get_latest_day_kline(table_name)
            
            if not latest_kline_result or latest_kline_result.get('message') != 'success':
                return {
                    'success': False,
                    'message': latest_kline_result.get('message', '获取最新K线数据失败')
                }
            
            latest_kline = latest_kline_result.get('kline_data')
            if not latest_kline:
                return {
                    'success': False,
                    'message': '没有最新K线数据'
                }
            
            # 2. 获取历史K线数据（用于MA、MACD等指标）
            kline_data_result = self.kline_service.get_kline_data(table_name, 'day')
            
            # get_kline_data直接返回data字典，不包含code字段
            if not kline_data_result:
                return {
                    'success': False,
                    'message': '获取历史K线数据失败'
                }
            
            kline_data = kline_data_result.get('klines', [])
            
            # 3. 获取前一交易日的赔率分（用于策略1）
            previous_daily_chance = self._get_previous_daily_chance(stock_code, latest_kline)
            
            day_win_ratio_score = 0
            week_win_ratio_score = 0
            total_win_ratio_score = 0
            
            if previous_daily_chance:
                day_win_ratio_score = previous_daily_chance.day_win_ratio_score or 0
                week_win_ratio_score = previous_daily_chance.week_win_ratio_score or 0
                total_win_ratio_score = previous_daily_chance.total_win_ratio_score or 0
            
            logger.info(f"  前一日赔率分 - 日:{day_win_ratio_score:.2f}, 周:{week_win_ratio_score:.2f}, 总:{total_win_ratio_score:.2f}")
            
            # 4. 获取预测成交量和成交量类型
            if not predicted_volume:
                volume_result = self.kline_service.predict_today_volume(table_name)
                predicted_volume = volume_result.get('predicted_volume')
            
            if not volume_type and predicted_volume:
                from domain.services.volume_type_service import VolumeTypeService
                volume_type = VolumeTypeService.calculate_volume_type_with_predicted(
                    table_name, predicted_volume
                )
            
            logger.info(f"  预测成交量: {predicted_volume}, 成交量类型: {volume_type}")
            
            # 5. 使用全局缓存管理器（单例模式，避免重复查询）
            from application.services.cr_cache_manager import get_cr_cache_manager
            
            cache_manager = get_cr_cache_manager()
            
            # 获取带缓存的CR策略服务（如果缓存不存在会自动初始化）
            cached_cr_service = cache_manager.get_cr_service(stock_code)
            
            logger.debug(f"  ✅ 使用缓存的CR服务: {stock_code}")
            
            # 6. 准备计算所需的数据
            current_kline = {
                'date': latest_kline['time'],
                'open': latest_kline['open'],
                'close': latest_kline['close'],
                'high': latest_kline['high'],
                'low': latest_kline['low'],
                'volume': predicted_volume if predicted_volume else latest_kline['volume'],
                'ma5': latest_kline.get('ma5'),
                'ma10': latest_kline.get('ma10'),
                'ma20': latest_kline.get('ma20'),
                'dif': latest_kline.get('dif'),
                'dea': latest_kline.get('dea'),
                'macd': latest_kline.get('macd'),
                'volume_type': volume_type
            }
            
            # 7. 获取MA和MACD数据
            ma_data = kline_data_result.get('ma', {})
            macd_data = kline_data_result.get('macd', {})
            
            # 8. 计算策略1的C点（使用缓存的CR服务）
            strategy1_result = self._check_strategy1_c_point(
                stock_code,
                current_kline['date'],
                volume_type,
                total_win_ratio_score,
                cached_cr_service  # 传入缓存的服务
            )
            
            # 9. 计算策略2的C点
            strategy2_result = self._check_strategy2_c_point(
                stock_code,
                current_kline['date'],
                current_kline['close'],
                ma_data,
                macd_data,
                volume_type,
                kline_data
            )
            
            # 10. 检查R点
            r_point_result = self._check_r_point(
                stock_code,
                current_kline['date'],
                ma_data,
                macd_data,
                kline_data
            )
            
            # 11. 不再需要清空缓存（全局缓存会自动管理）
            
            # 12. 组装返回结果
            result = {
                'success': True,
                'date': current_kline['date'],
                'stock_code': stock_code,
                'kline': {
                    'open': current_kline['open'],
                    'close': current_kline['close'],
                    'high': current_kline['high'],
                    'low': current_kline['low'],
                    'volume': current_kline['volume']
                },
                'predicted_volume': predicted_volume,
                'volume_type': volume_type,
                'previous_day_scores': {
                    'day': day_win_ratio_score,
                    'week': week_win_ratio_score,
                    'total': total_win_ratio_score
                },
                'strategy1': strategy1_result,
                'strategy2': strategy2_result,
                'r_point': r_point_result
            }
            
            logger.info(f"✅ 最新一天CR点计算完成")
            logger.info(f"  策略1: {'触发C点' if strategy1_result.get('is_c_point') else '未触发'} (分数:{strategy1_result.get('score', 0):.2f})")
            logger.info(f"  策略2: {'触发C点' if strategy2_result.get('is_c_point') else '未触发'} (分数:{strategy2_result.get('score', 0):.2f})")
            logger.info(f"  R点: {'触发' if r_point_result.get('is_r_point') else '未触发'}")
            
            return result
            
        except Exception as e:
            logger.error(f"计算最新一天CR点失败: {stock_code}, {e}", exc_info=True)
            return {
                'success': False,
                'message': str(e)
            }
    
    def _get_previous_daily_chance(self, stock_code: str, latest_kline: Dict):
        """获取前一交易日的每日机会数据"""
        try:
            # 获取最近的每日机会数据（按日期降序）
            daily_chances = self.daily_chance_service.get_daily_chance_by_stock(stock_code)
            
            if not daily_chances:
                logger.warning(f"  未找到每日机会数据: {stock_code}")
                return None
            
            logger.info(f"  获取到 {len(daily_chances)} 条每日机会记录")
            
            # 获取最新K线的日期
            latest_date = latest_kline['time'].split(' ')[0] if isinstance(latest_kline['time'], str) else latest_kline['time'].strftime('%Y-%m-%d')
            logger.info(f"  最新K线日期: {latest_date}")
            
            # daily_chances已经按日期降序排列，找到第一个小于最新日期的记录
            for dc in daily_chances:
                dc_date = dc.date.strftime('%Y-%m-%d') if hasattr(dc.date, 'strftime') else str(dc.date).split(' ')[0]
                logger.info(f"  检查日期: {dc_date} < {latest_date}?")
                
                if dc_date < latest_date:
                    logger.info(f"  ✅ 找到前一交易日数据: {dc_date}, 赔率总分={dc.total_win_ratio_score}")
                    return dc
            
            logger.warning(f"  未找到前一交易日数据（所有数据都>=最新日期）")
            return None
            
        except Exception as e:
            logger.error(f"获取前一交易日数据失败: {e}", exc_info=True)
            return None
    
    def _check_strategy1_c_point(
        self, 
        stock_code: str,
        date_str: str,
        volume_type: Optional[str],
        total_win_ratio_score: float,
        cr_service = None  # 使用传入的缓存服务
    ) -> Dict:
        """检查策略1的C点"""
        try:
            # 将日期字符串转换为datetime对象
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 使用传入的CR服务（带缓存）或默认服务
            service = cr_service if cr_service else self.cr_strategy_service
            
            # 调用CR策略服务检查C点
            # 返回: (是否触发, 最终分, 策略描述, 插件列表, 基础分, 是否被插件否决)
            is_triggered, final_score, strategy_desc, plugins, base_score, is_rejected = \
                service.check_c_point_strategy_1(
                    stock_code,
                    date_obj,
                    volume_type,
                    total_win_ratio_score,
                    None,  # historical_r_points
                    None   # historical_c_points
                )
            
            return {
                'is_c_point': is_triggered,
                'is_rejected': is_rejected,
                'score': final_score,
                'base_score': base_score,
                'plugins': plugins,
                'threshold': 70
            }
            
        except Exception as e:
            logger.error(f"策略1检查失败: {e}", exc_info=True)
            return {
                'is_c_point': False,
                'score': 0,
                'base_score': 0,
                'plugins': [],
                'error': str(e)
            }
    
    def _check_strategy2_c_point(
        self, 
        stock_code: str,
        date_str: str,
        close_price: float,
        ma_data: Dict,
        macd_data: Dict,
        volume_type: Optional[str],
        kline_data: List[Dict]
    ) -> Dict:
        """检查策略2的C点"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 找到当前日期在kline_data中的索引
            current_index = len(kline_data) - 1  # 假设最新的在最后
            
            # 准备前30天数据
            daily_data_30 = kline_data[-30:] if len(kline_data) >= 30 else kline_data
            
            # 调用策略2服务
            # 返回: (是否触发, 总分, 详细原因)
            is_triggered, score, reason = self.strategy2_service.check_strategy2(
                stock_code,
                date_obj,
                close_price,
                ma_data,
                macd_data,
                volume_type,
                None,  # bullish_pattern 暂时不传
                daily_data_30,
                current_index
            )
            
            return {
                'is_c_point': is_triggered,
                'score': score,
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"策略2检查失败: {e}", exc_info=True)
            return {
                'is_c_point': False,
                'score': 0,
                'reason': '',
                'error': str(e)
            }
    
    def _check_r_point(
        self, 
        stock_code: str,
        date_str: str,
        ma_data: Dict,
        macd_data: Dict,
        kline_data: List[Dict]
    ) -> Dict:
        """检查R点"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 找到当前日期在kline_data中的索引
            current_index = len(kline_data) - 1
            
            # 调用R点服务
            # 返回: (是否触发R点, 触发的插件列表)
            is_triggered, triggered_plugins = self.r_point_service.check_r_point(
                stock_code,
                date_obj,
                None,  # c_point_date
                ma_data,
                macd_data,
                current_index,
                kline_data
            )
            
            return {
                'is_r_point': is_triggered,
                'plugins': [
                    {
                        'plugin_name': p.plugin_name,
                        'reason': p.reason
                    }
                    for p in triggered_plugins
                ] if triggered_plugins else []
            }
            
        except Exception as e:
            logger.error(f"R点检查失败: {e}", exc_info=True)
            return {
                'is_r_point': False,
                'plugins': [],
                'error': str(e)
            }

