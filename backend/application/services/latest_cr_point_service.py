"""最新一天CR点计算服务"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger
from domain.services.cr_strategy_service import CRStrategyService
from domain.services.strategy2_service import Strategy2Service
from domain.services.r_point_plugin_service import RPointPluginService
from pathlib import Path
import json
import csv
from infrastructure.persistence.database import DatabaseConnection

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
        volume_type: Optional[str] = None,
        stock_nature: Optional[str] = None,
        stock_name: Optional[str] = None,
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
            stock_name = stock_name or self._get_stock_name_by_code(stock_code)
            if self._is_blocked_stock(stock_code, stock_name):
                logger.info(f"跳过CR点计算（ST/B股）：{stock_code} {stock_name or ''}")
                latest_kline_result = self.kline_service.get_latest_day_kline(table_name)
                latest_kline = (latest_kline_result or {}).get('kline_data') or {}
                date_val = latest_kline.get('time') if isinstance(latest_kline, dict) else None
                return {
                    'success': True,
                    'message': 'skip_cr_for_st_or_b',
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'stock_nature': stock_nature or "波段",
                    'date': date_val,
                    'kline': latest_kline if isinstance(latest_kline, dict) else {},
                    'predicted_volume': None,
                    'volume_type': None,
                    'realtime_volume_type': None,
                    'volume_type_source': 'skipped',
                    'previous_day_scores': {},
                    'strategy1': {'is_c_point': False, 'score': 0, 'base_score': 0, 'plugins': [], 'threshold': 0},
                    'strategy2': {'is_c_point': False, 'score': 0, 'reason': '', 'threshold': 0},
                    'r_point': {'is_r_point': False, 'plugins': []},
                }
            logger.info(f"开始计算最新一天CR点: {stock_code}")
            resolved_nature = stock_nature
            
            # 🔥 重要：从table_name提取完整的stock_code（带市场前缀）
            # 例如: basic_data_sz300188 → SZ300188
            full_stock_code = stock_code
            # 检查stock_code是否已经有市场前缀（SZ/SH）
            if not stock_code.upper().startswith(('SZ', 'SH')):
                # 如果没有前缀，根据table_name添加
                if '_sz' in table_name.lower():
                    full_stock_code = f'SZ{stock_code}'
                elif '_sh' in table_name.lower():
                    full_stock_code = f'SH{stock_code}'
            
            logger.info(f"  完整股票代码: {full_stock_code} (用于查询b_daily_chance表)")
            
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
            
            # 2. 获取历史K线数据（用于MA、MACD等指标，排除今天）
            kline_data_result = self.kline_service.get_kline_data(table_name, 'day', exclude_today=True)
            
            # get_kline_data直接返回data字典，不包含code字段
            if not kline_data_result:
                return {
                    'success': False,
                    'message': '获取历史K线数据失败'
                }
            
            kline_data = kline_data_result.get('kline_data', [])  # 🔥 修复：字段名是 kline_data 不是 klines
            
            # 🔥 【新增】获取历史CR点数据（用于插件判断）
            logger.info(f"  🔥 开始获取历史CR点数据...")
            historical_c_points = []
            historical_r_points = []
            try:
                if kline_data:
                    # ✅ 性能优化（仅 latest_cr_points 接口生效）：
                    # 为了插件判断，仅计算最近 N 个交易日的历史CR点，避免全量历史循环
                    HISTORY_TRADING_DAYS = 90
                    if len(kline_data) > HISTORY_TRADING_DAYS:
                        kline_data_for_history = kline_data[-HISTORY_TRADING_DAYS:]
                        logger.info(f"  ✅ 历史CR点仅计算最近{HISTORY_TRADING_DAYS}个交易日: {len(kline_data)} -> {len(kline_data_for_history)}")
                    else:
                        kline_data_for_history = kline_data

                    # 转换为KLineData对象
                    from domain.models.kline import KLineData
                    from datetime import datetime as dt
                    
                    kline_objects = []
                    for kline in kline_data_for_history:
                        kline_obj = KLineData(
                            time=dt.strptime(kline['time'], '%Y-%m-%d %H:%M:%S'),
                            open=kline['open'],
                            high=kline['high'],
                            low=kline['low'],
                            close=kline['close'],
                            volume=kline['volume'],
                            liangbi=kline.get('liangbi', 0),
                            weibi=kline.get('weibi', 0)
                        )
                        kline_objects.append(kline_obj)
                    
                    # 获取历史成交量类型和多头组合
                    from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
                    daily_chance_repo = DailyChanceRepositoryImpl()
                    
                    volume_types_hist = {}
                    bullish_patterns_hist = {}
                    
                    start_date = kline_data_for_history[0]['time'].split(' ')[0]
                    end_date = kline_data_for_history[-1]['time'].split(' ')[0]
                    
                    daily_chances = daily_chance_repo.find_by_stock_code(
                        full_stock_code, start_date, end_date
                    )
                    
                    for dc in daily_chances:
                        date_str = dc.date.strftime('%Y-%m-%d')
                        if dc.volume_type:
                            volume_types_hist[date_str] = dc.volume_type
                        if dc.bullish_pattern:
                            bullish_patterns_hist[date_str] = dc.bullish_pattern
                    
                    # 使用CRPointService分析历史CR点
                    from application.services.cr_point_service import CRPointService
                    cr_service = CRPointService()
                    
                    # ⚠️ 注意：CRPointService.analyze_cr_points 内部的策略2会用 index 访问 MA/MACD 数组
                    # 因此这里必须把 MA/MACD 数据裁剪到与 kline_objects 相同长度，避免索引错位/越界
                    ma_hist = kline_data_result.get('ma', {}) or {}
                    macd_hist = kline_data_result.get('macd', {}) or {}
                    n_hist = len(kline_objects)

                    ma_hist_sliced = {}
                    for key, arr in ma_hist.items():
                        if isinstance(arr, list) and len(arr) >= n_hist:
                            ma_hist_sliced[key] = arr[-n_hist:]
                        else:
                            ma_hist_sliced[key] = arr

                    macd_hist_sliced = {}
                    for key, arr in macd_hist.items():
                        if isinstance(arr, list) and len(arr) >= n_hist:
                            macd_hist_sliced[key] = arr[-n_hist:]
                        else:
                            macd_hist_sliced[key] = arr

                    logger.info(f"  🔥 调用 analyze_cr_points 分析历史数据（最近{n_hist}条日K）...")
                    cr_result = cr_service.analyze_cr_points(
                        full_stock_code,
                        '',  # stock_name
                        kline_objects,
                        ma_data=ma_hist_sliced,
                        macd_data=macd_hist_sliced,
                        volume_types=volume_types_hist,
                        bullish_patterns=bullish_patterns_hist
                    )
                    
                    # 提取历史C点和R点
                    historical_c_points = cr_result.get('c_points', []) + cr_result.get('strategy2_c_points', [])
                    historical_r_points = cr_result.get('r_points', [])
                    
                    logger.info(f"  ✅ 历史CR点数据获取成功: C点 {len(historical_c_points)} 个, R点 {len(historical_r_points)} 个")
                else:
                    logger.warning(f"  ⚠️ 没有历史K线数据")
            except Exception as e:
                logger.error(f"  ❌ 获取历史CR点数据失败: {e}", exc_info=True)
                # 继续执行，使用空列表
            
            # 🔥 重要：将最新一天的数据追加到kline_data中
            # 因为最新一天的数据还没写入数据库，需要手动追加
            latest_date = latest_kline['time']
            
            # 检查kline_data最后一条数据的日期，避免重复追加
            if kline_data:
                last_kline_date = kline_data[-1].get('time', '').split(' ')[0] if isinstance(kline_data[-1].get('time'), str) else kline_data[-1].get('time', '')
                
                # 如果最后一条数据不是最新日期，则追加
                if last_kline_date != latest_date:
                    logger.info(f"  追加最新一天数据到kline_data: {latest_date}")
                    kline_data.append({
                        'time': latest_date,
                        'open': latest_kline['open'],
                        'close': latest_kline['close'],
                        'high': latest_kline['high'],
                        'low': latest_kline['low'],
                        'volume': predicted_volume if predicted_volume else latest_kline['volume']
                    })
                    
                    # 重新计算MA和MACD（包含最新一天）
                    from domain.services.ma_service import MAService
                    from domain.services.macd_service import MACDService
                    
                    ma_service = MAService()
                    macd_service = MACDService()
                    
                    # 提取价格和成交量数据
                    closes = [k.get('close') for k in kline_data]
                    
                    # 重新计算MA
                    ma5 = ma_service.calculate_sma(closes, 5)
                    ma10 = ma_service.calculate_sma(closes, 10)
                    ma20 = ma_service.calculate_sma(closes, 20)
                    
                    # 重新计算MACD（返回字典）
                    macd_result = macd_service.calculate_macd(closes)
                    
                    # 更新kline_data_result中的MA和MACD数据
                    kline_data_result['ma'] = {
                        'ma5': ma5,
                        'ma10': ma10,
                        'ma20': ma20
                    }
                    kline_data_result['macd'] = macd_result
                    
                    logger.info(f"  ✅ 重新计算MA和MACD，包含最新一天 {latest_date}")
                    # 安全地格式化MA数据
                    ma5_val = f"{ma5[-1]:.2f}" if ma5[-1] is not None else 'None'
                    ma10_val = f"{ma10[-1]:.2f}" if ma10[-1] is not None else 'None'
                    ma20_val = f"{ma20[-1]:.2f}" if ma20[-1] is not None else 'None'
                    logger.info(f"     MA5={ma5_val}, MA10={ma10_val}, MA20={ma20_val}")
                    # 安全地格式化MACD数据
                    dif_list = macd_result.get('dif', [])
                    dea_list = macd_result.get('dea', [])
                    macd_list = macd_result.get('macd', [])
                    if dif_list and dea_list and macd_list:
                        dif_val = f"{dif_list[-1]:.4f}" if isinstance(dif_list[-1], (int, float)) and dif_list[-1] is not None else 'None'
                        dea_val = f"{dea_list[-1]:.4f}" if isinstance(dea_list[-1], (int, float)) and dea_list[-1] is not None else 'None'
                        macd_val = f"{macd_list[-1]:.4f}" if isinstance(macd_list[-1], (int, float)) and macd_list[-1] is not None else 'None'
                        logger.info(f"     DIF={dif_val}, DEA={dea_val}, MACD={macd_val}")
            
            # 3. 获取前一交易日的赔率分（用于策略1）
            previous_daily_chance = self._get_previous_daily_chance(full_stock_code, latest_kline)
            
            day_win_ratio_score = 0
            week_win_ratio_score = 0
            total_win_ratio_score = 0
            
            has_historical_data = False
            if previous_daily_chance:
                day_win_ratio_score = previous_daily_chance.day_win_ratio_score or 0
                week_win_ratio_score = previous_daily_chance.week_win_ratio_score or 0
                total_win_ratio_score = previous_daily_chance.total_win_ratio_score or 0
                has_historical_data = True
            else:
                logger.warning(f"  ⚠️ 未找到前一天的历史评分数据，建议先执行历史CR点分析")
            
            logger.info(f"  前一日赔率分 - 日:{day_win_ratio_score:.2f}, 周:{week_win_ratio_score:.2f}, 总:{total_win_ratio_score:.2f}")
            
            if resolved_nature is None and previous_daily_chance:
                resolved_nature = getattr(previous_daily_chance, "stock_nature", None)
            resolved_nature = resolved_nature or "波段"
            logger.info(f"  股性: {resolved_nature}")
            
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
            logger.info(f"  🔥 准备计算策略1: 成交量类型={volume_type}, 赔率总分={total_win_ratio_score:.2f}")
            strategy1_result = self._check_strategy1_c_point(
                full_stock_code,  # 🔥 使用带前缀的完整代码
                current_kline['date'],
                volume_type,
                total_win_ratio_score,
                cached_cr_service,  # 传入缓存的服务
                historical_c_points,  # 传入历史C点
                historical_r_points,  # 传入历史R点
                stock_nature=resolved_nature
            )
            logger.info(f"  🔥 策略1计算结果: 基础分={strategy1_result.get('base_score', 0):.2f}, 最终分={strategy1_result.get('score', 0):.2f}")
            
            # 9. 获取多头K线组合（用于策略2的K线组合评分）
            bullish_pattern = None
            if len(kline_data) >= 3:
                from domain.services.bullish_pattern_service import BullishPatternService
                from datetime import datetime
                
                # 将日期字符串转换为datetime对象
                target_date = datetime.strptime(current_kline['date'], '%Y-%m-%d') if isinstance(current_kline['date'], str) else current_kline['date']
                
                # 调用正确的方法名：identify_bullish_patterns
                patterns = BullishPatternService.identify_bullish_patterns(
                    full_stock_code, table_name, target_date
                )
                if patterns:
                    bullish_pattern = ','.join(patterns)  # 多个组合用逗号连接
                    logger.info(f"  检测到多头K线组合: {bullish_pattern}")
            
            # 10. 计算策略2的C点
            logger.info(f"  🔥 准备计算策略2: kline_data长度={len(kline_data)}")
            if kline_data:
                logger.info(f"     第一条: {kline_data[0].get('time', 'N/A')}")
                logger.info(f"     最后一条: {kline_data[-1].get('time', 'N/A')}")
            
            strategy2_result = self._check_strategy2_c_point(
                full_stock_code,  # 🔥 使用带前缀的完整代码
                current_kline['date'],
                current_kline['close'],
                ma_data,
                macd_data,
                volume_type,
                bullish_pattern,
                kline_data,
                stock_nature=resolved_nature
            )
            
            # 11. 检查R点
            # 计算最近的C点日期 & 最近有效点类型（C / R），供插件2使用
            def _extract_trigger_date(point):
                if point is None:
                    return None
                val = point.get('trigger_date') if isinstance(point, dict) else getattr(point, 'trigger_date', None)
                if isinstance(val, str):
                    try:
                        return datetime.strptime(val.split(' ')[0], '%Y-%m-%d')
                    except Exception:
                        return None
                if hasattr(val, 'strftime'):
                    return val
                return None

            last_c_point_date = None
            last_valid_point_type = None
            last_valid_point_date = None

            if historical_c_points:
                last_c = historical_c_points[-1]
                last_c_point_date = _extract_trigger_date(last_c)
                if last_c_point_date:
                    last_valid_point_type = 'C'
                    last_valid_point_date = last_c_point_date

            if historical_r_points:
                last_r = historical_r_points[-1]
                last_r_date = _extract_trigger_date(last_r)
                # 如果最近的点是R且日期更晚，则覆盖 last_valid_point_type/date
                if last_r_date and (last_valid_point_date is None or last_r_date > last_valid_point_date):
                    last_valid_point_type = 'R'
                    last_valid_point_date = last_r_date

            r_point_result = self._check_r_point(
                full_stock_code,  # 🔥 使用带前缀的完整代码
                current_kline['date'],
                ma_data,
                macd_data,
                kline_data,
                last_c_point_date,  # 传入最近的C点日期
                last_valid_point_type=last_valid_point_type  # 传入最近有效点类型（允许插件2生效）
            )
            
            # 12. 不再需要清空缓存（全局缓存会自动管理）
            
            # 13. 组装返回结果
            volume_type_source = "predicted" if predicted_volume else "historical"

            result = {
                'success': True,
                'date': current_kline['date'],
                'stock_code': stock_code,
                'stock_nature': resolved_nature,
                'kline': {
                    'open': current_kline['open'],
                    'close': current_kline['close'],
                    'high': current_kline['high'],
                    'low': current_kline['low'],
                    'volume': current_kline['volume']
                },
                'predicted_volume': predicted_volume,
                'volume_type': volume_type,
                'realtime_volume_type': volume_type,  # 兼容前端展示实时成交量类型
                'volume_type_source': volume_type_source,
                'previous_day_scores': {
                    'day': day_win_ratio_score,
                    'week': week_win_ratio_score,
                    'total': total_win_ratio_score,
                    'has_historical_data': has_historical_data  # 🔥 新增：是否有历史评分数据
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
        cr_service = None,  # 使用传入的缓存服务
        historical_c_points: Optional[List] = None,  # 历史C点
        historical_r_points: Optional[List] = None,  # 历史R点
        stock_nature: Optional[str] = None
    ) -> Dict:
        """检查策略1的C点"""
        try:
            logger.info(f"🔍 [Strategy1] 开始检查C点:")
            logger.info(f"  📊 输入参数:")
            logger.info(f"    - stock_code: {stock_code}")
            logger.info(f"    - date_str: {date_str}")
            logger.info(f"    - volume_type: {volume_type}")
            logger.info(f"    - total_win_ratio_score: {total_win_ratio_score}")
            logger.info(f"    - cr_service: {'传入的服务' if cr_service else '默认服务'}")
            logger.info(f"    - historical_c_points: {len(historical_c_points) if historical_c_points else 0} 个")
            logger.info(f"    - historical_r_points: {len(historical_r_points) if historical_r_points else 0} 个")
            
            # 将日期字符串转换为datetime对象
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 使用传入的CR服务（带缓存）或默认服务
            service = cr_service if cr_service else self.cr_strategy_service
            
            logger.info(f"  🎯 准备调用 check_c_point_strategy_1...")
            
            # 调用CR策略服务检查C点
            # 返回: (是否触发, 最终分, 策略描述, 插件列表, 基础分, 是否被插件否决)
            is_triggered, final_score, strategy_desc, plugins, base_score, is_rejected = \
                service.check_c_point_strategy_1(
                    stock_code,
                    date_obj,
                    volume_type,
                    total_win_ratio_score,
                    historical_r_points,  # 传入历史R点
                    historical_c_points,  # 传入历史C点
                    stock_nature=stock_nature
                )
            
            logger.info(f"  ✅ [Strategy1] 计算完成:")
            logger.info(f"    - base_score: {base_score}")
            logger.info(f"    - final_score: {final_score}")
            logger.info(f"    - is_triggered: {is_triggered}")
            logger.info(f"    - is_rejected: {is_rejected}")
            logger.info(f"    - plugins: {plugins}")
            
            return {
                'is_c_point': is_triggered,
                'is_rejected': is_rejected,
                'score': final_score,
                'base_score': base_score,
                'plugins': plugins,
                'threshold': service.config_service.get_strategy1_threshold(stock_nature)
            }
            
        except Exception as e:
            logger.error(f"❌ [Strategy1] 策略1检查失败: {e}", exc_info=True)
            logger.error(f"  📊 失败时的参数:")
            logger.error(f"    - stock_code: {stock_code}")
            logger.error(f"    - date_str: {date_str}")
            logger.error(f"    - volume_type: {volume_type}")
            logger.error(f"    - total_win_ratio_score: {total_win_ratio_score}")
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
        bullish_pattern: Optional[str],
        kline_data: List[Dict],
        stock_nature: Optional[str] = None
    ) -> Dict:
        """检查策略2的C点"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 找到当前日期在kline_data中的索引（最新的在最后）
            current_index = len(kline_data) - 1
            
            logger.info(f"  策略2计算: 当前索引={current_index}, K线数据总数={len(kline_data)}, 当前日期={date_str}")
            logger.info(f"  MA数据长度: ma5={len(ma_data.get('ma5', []))}, ma10={len(ma_data.get('ma10', []))}, ma20={len(ma_data.get('ma20', []))}")
            logger.info(f"  MACD数据长度: dif={len(macd_data.get('dif', []))}, dea={len(macd_data.get('dea', []))}, macd={len(macd_data.get('macd', []))}")
            
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
                bullish_pattern,  # 🔥 传入多头K线组合
                daily_data_30,
                current_index,
                prev_day_has_r=False,
                strategy1_reject_by_penalty_plugins=False,
                stock_nature=stock_nature
            )
            
            return {
                'is_c_point': is_triggered,
                'score': score,
                'reason': reason,
                'threshold': self.strategy2_service.config_service.get_strategy2_threshold(stock_nature)
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
        kline_data: List[Dict],
        c_point_date = None,  # 最近的C点日期
        last_valid_point_type: Optional[str] = None  # 最近有效点类型（C/R）
    ) -> Dict:
        """检查R点"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')

            # 将 kline_data(dict) 转为 KLineData 对象列表
            # 重要：R点插件的部分逻辑（如箱体回踩）会直接访问 kline_data[i].high/low
            from domain.models.kline import KLineData as DomainKLineData

            def _parse_dt(value: str) -> datetime:
                if not value:
                    return date_obj
                candidate = str(value).replace("T", " ").split(".")[0]
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(candidate, fmt)
                    except ValueError:
                        continue
                return date_obj

            kline_objects = []
            for k in kline_data:
                try:
                    kline_objects.append(
                        DomainKLineData(
                            time=_parse_dt(k.get("time")),
                            open=float(k.get("open", 0) or 0),
                            high=float(k.get("high", 0) or 0),
                            low=float(k.get("low", 0) or 0),
                            close=float(k.get("close", 0) or 0),
                            volume=float(k.get("volume", 0) or 0),
                            liangbi=float(k.get("liangbi", 0) or 0),
                            weibi=float(k.get("weibi", 0) or 0),
                        )
                    )
                except Exception:
                    continue

            # 找到当前日期在kline_data中的索引（转换后列表）
            current_index = len(kline_objects) - 1
            
            # 转换c_point_date为datetime对象
            c_point_date_obj = None
            if c_point_date:
                if isinstance(c_point_date, str):
                    c_point_date_obj = datetime.strptime(c_point_date.split(' ')[0], '%Y-%m-%d')
                elif hasattr(c_point_date, 'strftime'):
                    c_point_date_obj = c_point_date
            
            logger.info(f"  🔥 检查R点: 最近C点日期={c_point_date_obj}")
            
            # 调用R点服务
            # 返回: (是否触发R点, 触发的插件列表)
            is_triggered, triggered_plugins = self.r_point_service.check_r_point(
                stock_code,
                date_obj,
                c_point_date_obj,  # 传入最近的C点日期
                ma_data,
                macd_data,
                current_index,
                kline_objects,
                last_valid_point_type=last_valid_point_type
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

    @staticmethod
    def _is_blocked_stock(stock_code: str, stock_name: Optional[str] = None) -> bool:
        """判定是否为需跳过CR计算的股票：B股(900/200开头)或名称含ST/*ST"""
        code_upper = (stock_code or "").upper()
        pure_code = code_upper
        if code_upper.startswith(("SZ", "SH")) and len(code_upper) > 2:
            pure_code = code_upper[2:]
        if pure_code.startswith(("900", "200")):
            return True
        name_upper = (stock_name or "").upper()
        if "ST" in name_upper:
            return True
        return False

    @staticmethod
    def _get_stock_name_by_code(stock_code: str) -> Optional[str]:
        """按code查询名称，多级兜底，避免未传名称时漏判ST"""
        if not stock_code:
            return None

        # 1) 数据库 all_stock
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM all_stock WHERE LOWER(code)=LOWER(%s) LIMIT 1",
                    (stock_code,)
                )
                row = cursor.fetchone()
                if row:
                    return row[0] if isinstance(row, (list, tuple)) else row.get("name")
        except Exception:
            pass

        # 2) 配置文件 backend/infrastructure/config/stock_config.json
        try:
            config_path = Path(__file__).resolve().parent.parent.parent / "infrastructure" / "config" / "stock_config.json"
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for stock_list in data.values():
                        for s in stock_list:
                            if str(s.get("code", "")).lower() == str(stock_code).lower():
                                return s.get("name")
        except Exception:
            pass

        # 3) CSV stock_list.csv（在项目根目录下）
        try:
            csv_path = Path(__file__).resolve().parent.parent.parent.parent / "stock_list.csv"
            if csv_path.exists():
                with csv_path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("code", "")).lower() == str(stock_code).lower():
                            return row.get("name")
        except Exception:
            pass

        return None

