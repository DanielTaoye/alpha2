"""R点插件服务 - 风险信号检测"""
from typing import Tuple, List, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class RPointPluginResult:
    """R点插件结果"""
    def __init__(self, plugin_name: str, triggered: bool, reason: str):
        self.plugin_name = plugin_name  # 插件名称
        self.triggered = triggered  # 是否触发
        self.reason = reason  # 触发原因
    
    def to_dict(self):
        return {
            'pluginName': self.plugin_name,
            'triggered': self.triggered,
            'reason': self.reason
        }


class RPointPluginService:
    """R点插件服务 - 风险信号检测"""
    
    def __init__(self):
        """初始化R点插件服务"""
        from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
        from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
        from domain.services.config_service import ConfigService
        self.daily_repo = DailyRepositoryImpl()
        self.daily_chance_repo = DailyChanceRepositoryImpl()
        self.config_service = ConfigService()
        # 数据缓存
        self._daily_cache = {}  # {date_str: DailyData}
        self._daily_chance_cache = {}  # {date_str: DailyChance}
    
    def init_cache(self, stock_code: str, start_date: str, end_date: str):
        """
        初始化数据缓存（批量查询）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始初始化R点插件缓存: {stock_code} {start_date} 至 {end_date}")
        
        # 批量查询 daily 数据
        daily_list = self.daily_repo.find_by_date_range(stock_code, start_date, end_date)
        self._daily_cache = {}
        for daily in daily_list:
            date_str = daily.date.strftime('%Y-%m-%d') if isinstance(daily.date, datetime) else str(daily.date)
            self._daily_cache[date_str] = daily
        
        # 批量查询 daily_chance 数据
        daily_chance_list = self.daily_chance_repo.find_by_stock_code(stock_code, start_date, end_date)
        self._daily_chance_cache = {}
        for dc in daily_chance_list:
            date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
            self._daily_chance_cache[date_str] = dc
        
        logger.info(f"R点插件缓存初始化完成: daily={len(self._daily_cache)}条, daily_chance={len(self._daily_chance_cache)}条")
    
    def clear_cache(self):
        """清空缓存"""
        self._daily_cache = {}
        self._daily_chance_cache = {}
    
    def check_r_point(self, stock_code: str, date: datetime, c_point_date: Optional[datetime] = None,
                     ma_data: Optional[dict] = None, macd_data: Optional[dict] = None, 
                     current_index: Optional[int] = None, kline_data: Optional[list] = None) -> Tuple[bool, List[RPointPluginResult]]:
        """
        检查是否触发R点（卖出信号）
        
        Args:
            stock_code: 股票代码
            date: 检查日期
            c_point_date: C点触发日期（用于"上冲乏力"判断）
            ma_data: MA均线数据（可选，用于高位发R插件）
            macd_data: MACD数据（可选，用于高位发R插件）
            current_index: 当前K线索引（可选，用于高位发R、箱体回踩插件）
            kline_data: K线数据列表（可选，用于箱体回踩插件）
            
        Returns:
            Tuple[bool, List[RPointPluginResult]]: (是否触发R点, 触发的插件列表)
        """
        triggered_plugins = []
        
        # 插件1: 乖离率偏离
        plugin1 = self._check_deviation(stock_code, date)
        if plugin1.triggered:
            triggered_plugins.append(plugin1)
            logger.info(f"[R点插件-乖离率偏离] {stock_code} {date}: {plugin1.reason}")
            return True, triggered_plugins
        
        # 插件2: 临近压力位滞涨
        plugin2 = self._check_pressure_stagnation(stock_code, date, c_point_date)
        if plugin2.triggered:
            triggered_plugins.append(plugin2)
            logger.info(f"[R点插件-临近压力位滞涨] {stock_code} {date}: {plugin2.reason}")
            return True, triggered_plugins
        
        # 插件3: 基本面突发利空
        plugin3 = self._check_fundamental_negative(stock_code, date)
        if plugin3.triggered:
            triggered_plugins.append(plugin3)
            logger.info(f"[R点插件-基本面突发利空] {stock_code} {date}: {plugin3.reason}")
            return True, triggered_plugins
        
        # 插件4: 上冲乏力
        if c_point_date:
            plugin4 = self._check_weak_breakout(stock_code, date, c_point_date)
            if plugin4.triggered:
                triggered_plugins.append(plugin4)
                logger.info(f"[R点插件-上冲乏力] {stock_code} {date}: {plugin4.reason}")
                return True, triggered_plugins
        
        # 插件5: 跌破支撑位
        plugin5 = self._check_break_support(stock_code, date)
        if plugin5.triggered:
            triggered_plugins.append(plugin5)
            logger.info(f"[R点插件-跌破支撑位] {stock_code} {date}: {plugin5.reason}")
            return True, triggered_plugins
        
        # 插件6: 高位发R
        if ma_data and macd_data and current_index is not None:
            plugin6 = self._check_high_position_r(stock_code, date, ma_data, macd_data, current_index)
            if plugin6.triggered:
                triggered_plugins.append(plugin6)
                logger.info(f"[R点插件-高位发R] {stock_code} {date}: {plugin6.reason}")
                return True, triggered_plugins
        
        # 插件7: 箱体回踩被跌破
        if macd_data and current_index is not None and kline_data is not None:
            plugin7 = self._check_box_breakdown(stock_code, date, macd_data, current_index, kline_data)
            if plugin7.triggered:
                triggered_plugins.append(plugin7)
                logger.info(f"[R点插件-箱体回踩被跌破] {stock_code} {date}: {plugin7.reason}")
                return True, triggered_plugins
        
        return False, triggered_plugins
    
    def _check_deviation(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件1: 乖离率偏离
        
        包含6个子条件：
        1. 连续2个以上涨停
        2. 前3日累计涨幅过大
        3. 前5日累计涨幅过大
        4. 连续5连阳+阶段涨幅过大
        5. 前15日累计涨幅过大
        6. 前20日累计涨幅过大
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 判断主板还是非主板
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 获取当日daily_chance（成交量类型、空头组合）
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            
            # 如果没有daily_chance数据，无法判断成交量和空头组合，记录日志
            if not current_chance:
                logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 无daily_chance数据，跳过检查")
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 获取历史数据
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 20:
                logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 历史数据不足20天({len(prev_dates)}天)")
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 判断当日是否放量（XYH）或（XYZH）
            is_volume_xyz = self._check_volume_type(current_chance, ['X', 'Y', 'Z'])
            is_volume_xyh = self._check_volume_type(current_chance, ['X', 'Y', 'H'])
            is_volume_xyzh = self._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            
            # 判断当日K线形态
            matched_patterns = self._check_bearish_kline_patterns(current_data, stock_code)
            is_bearish_kline = len(matched_patterns) > 0
            has_bearish_pattern = self._check_bearish_pattern(current_chance)
            
            # 调试日志
            logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 基础检查: volume_type={current_chance.volume_type}, "
                        f"is_volume_xyh={is_volume_xyh}, is_volume_xyzh={is_volume_xyzh}, "
                        f"is_bearish_kline={is_bearish_kline}, matched_patterns={matched_patterns}, "
                        f"has_bearish_pattern={has_bearish_pattern}")
            
            # 获取前N日数据
            prev_data_list = []
            for prev_date in prev_dates[:20]:
                data = self._daily_cache.get(prev_date)
                if not data:
                    data = self.daily_repo.find_by_date(stock_code, prev_date)
                if data:
                    prev_data_list.append(data)
            
            if len(prev_data_list) < 5:
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 计算涨跌幅
            change_pcts = []
            for data in prev_data_list:
                if data.pre_close and data.pre_close > 0:
                    pct = (data.close - data.pre_close) / data.pre_close * 100
                    change_pcts.append(pct)
                else:
                    change_pcts.append(0)
            
            # === 条件1: 连续2个以上涨停 ===
            limit_threshold = 9.9 if is_main_board else 19.8
            consecutive_limits = 0
            for pct in change_pcts[:5]:
                if pct >= limit_threshold:
                    consecutive_limits += 1
                else:
                    break
            
            if consecutive_limits >= 2:
                logger.debug(f"[R点-乖离率偏离-条件1] {stock_code} {date_str} 连续{consecutive_limits}个涨停, "
                            f"is_volume_xyh={is_volume_xyh}, is_bearish_kline={is_bearish_kline}, matched_patterns={matched_patterns}")
                if is_volume_xyh and is_bearish_kline:
                    pattern_desc = "、".join(matched_patterns)
                    # 计算振幅
                    amplitude = 0
                    if current_data.pre_close and current_data.pre_close > 0:
                        amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                    return RPointPluginResult(
                        "乖离率偏离",
                        True,
                        f"条件1: 连续{consecutive_limits}个涨停+放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                    )
            
            # === 条件2: 前3日累计涨幅过大 ===
            if len(change_pcts) >= 3:
                cum_3days = sum(change_pcts[:3])
                threshold_3days = 15 if is_main_board else 20
                if cum_3days > threshold_3days:
                    logger.debug(f"[R点-乖离率偏离-条件2] {stock_code} {date_str} 前3日涨幅{cum_3days:.2f}%>{threshold_3days}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_kline={is_bearish_kline}, matched_patterns={matched_patterns}")
                    if is_volume_xyh and is_bearish_kline:
                        pattern_desc = "、".join(matched_patterns)
                        # 计算振幅
                        amplitude = 0
                        if current_data.pre_close and current_data.pre_close > 0:
                            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件2: 前3日涨幅{cum_3days:.2f}%+放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                        )
            
            # === 条件3: 前5日累计涨幅过大 ===
            if len(change_pcts) >= 5:
                cum_5days = sum(change_pcts[:5])
                threshold_5days = 20 if is_main_board else 25
                if cum_5days > threshold_5days:
                    logger.debug(f"[R点-乖离率偏离-条件3] {stock_code} {date_str} 前5日涨幅{cum_5days:.2f}%>{threshold_5days}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_kline={is_bearish_kline}, matched_patterns={matched_patterns}")
                    if is_volume_xyh and is_bearish_kline:
                        pattern_desc = "、".join(matched_patterns)
                        # 计算振幅
                        amplitude = 0
                        if current_data.pre_close and current_data.pre_close > 0:
                            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件3: 前5日涨幅{cum_5days:.2f}%+放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                        )
            
            # === 条件4: 连续5连阳+涨幅过大 ===
            if len(prev_data_list) >= 5:
                all_bullish = all(prev_data_list[i].close >= prev_data_list[i].open for i in range(5))
                cum_5days_yang = sum(change_pcts[:5])
                threshold_yang = 20 if is_main_board else 25
                if all_bullish and cum_5days_yang > threshold_yang:
                    logger.debug(f"[R点-乖离率偏离-条件4] {stock_code} {date_str} 5连阳+涨幅{cum_5days_yang:.2f}%>{threshold_yang}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_kline={is_bearish_kline}, matched_patterns={matched_patterns}")
                    if is_volume_xyh and is_bearish_kline:
                        pattern_desc = "、".join(matched_patterns)
                        # 计算振幅
                        amplitude = 0
                        if current_data.pre_close and current_data.pre_close > 0:
                            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件4: 连续5连阳+涨幅{cum_5days_yang:.2f}%+放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                        )
            
            # === 条件5: 前15日累计涨幅>50% ===
            if len(change_pcts) >= 15:
                cum_15days = sum(change_pcts[:15])
                if cum_15days > 50:
                    logger.debug(f"[R点-乖离率偏离-条件5] {stock_code} {date_str} 前15日涨幅{cum_15days:.2f}%>50%, "
                                f"is_volume_xyzh={is_volume_xyzh}, is_bearish_kline={is_bearish_kline}, has_bearish_pattern={has_bearish_pattern}")
                    if is_volume_xyzh and (is_bearish_kline or has_bearish_pattern):
                        # 计算振幅
                        amplitude = 0
                        if current_data.pre_close and current_data.pre_close > 0:
                            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                        
                        # 组合描述
                        signal_desc = ""
                        if is_bearish_kline:
                            pattern_desc = "、".join(matched_patterns)
                            signal_desc = f"空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                        elif has_bearish_pattern:
                            bearish_patterns = current_chance.bearish_pattern.strip()
                            signal_desc = f"空头组合({bearish_patterns})"
                        
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件5: 前15日涨幅{cum_15days:.2f}%+放量+{signal_desc}"
                        )
            
            # === 条件6: 前20日累计涨幅>50% ===
            if len(change_pcts) >= 20:
                cum_20days = sum(change_pcts[:20])
                if cum_20days > 50:
                    logger.debug(f"[R点-乖离率偏离-条件6] {stock_code} {date_str} 前20日涨幅{cum_20days:.2f}%>50%, "
                                f"is_volume_xyzh={is_volume_xyzh}, is_bearish_kline={is_bearish_kline}, has_bearish_pattern={has_bearish_pattern}")
                    if is_volume_xyzh and (is_bearish_kline or has_bearish_pattern):
                        # 计算振幅
                        amplitude = 0
                        if current_data.pre_close and current_data.pre_close > 0:
                            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                        
                        # 组合描述
                        signal_desc = ""
                        if is_bearish_kline:
                            pattern_desc = "、".join(matched_patterns)
                            signal_desc = f"空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                        elif has_bearish_pattern:
                            bearish_patterns = current_chance.bearish_pattern.strip()
                            signal_desc = f"空头组合({bearish_patterns})"
                        
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件6: 前20日涨幅{cum_20days:.2f}%+放量+{signal_desc}"
                        )
            
            return RPointPluginResult("乖离率偏离", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-乖离率偏离检查失败: {e}")
            return RPointPluginResult("乖离率偏离", False, "")
    
    def _check_pressure_stagnation(self, stock_code: str, date: datetime, c_point_date: Optional[datetime] = None) -> RPointPluginResult:
        """
        插件2: 临近压力位滞涨
        
        前提条件（共同条件）：
        - 前一交易日日线赔率得分：短线<12分、波段<10分、中长线<8分，且不等于0
        - 当前股价距离压力线：0% < (压力线-股价)/股价 < 10%
        - 压力线价格从数据库读取后需除以100（数据库存储格式：1660代表16.60元）
        
        条件1: 前提条件 + 放量(XYZH) + 特定K线 + C点日开盘价<当日收盘价
        条件2(熊市): 前提条件 + 前3日无AXYZ放量 + 空头组合 + C点日开盘价<当日收盘价
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            c_data = None  # 初始化C点日数据
            
            # 判断主板还是非主板
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 获取当日daily_chance（用于获取股性和成交量类型）
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 获取股性
            stock_nature = current_chance.stock_nature or "波段"  # 默认波段
            
            # 获取前一交易日的数据，使用前一交易日的赔率得分来判断是否临近压力位
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if not prev_dates or len(prev_dates) < 1:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 使用前一交易日的日线赔率得分（距离压力位的空间）
            day_win_ratio_score = prev_chance.day_win_ratio_score or 0
            
            # 根据股性判断是否临近压力位
            # 要求：0 < 赔率得分 < 阈值（短线<12分、波段<10分、中长线<8分）
            pressure_threshold = self._get_pressure_threshold(stock_nature)
            is_near_pressure_by_score = 0 < day_win_ratio_score < pressure_threshold
            
            logger.info(f"[临近压力位滞涨-赔率检查] {stock_code} {date_str} 股性:{stock_nature}, 前日赔率:{day_win_ratio_score:.1f}, 阈值:{pressure_threshold}, 是否满足0<赔率<{pressure_threshold}: {is_near_pressure_by_score}")
            
            if not is_near_pressure_by_score:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 检查当前股价距离压力线的距离
            # 从配置中获取距离阈值（默认10%）
            distance_threshold = self.config_service.get_pressure_stagnation_distance_threshold()
            
            if prev_chance.pressure_price and prev_chance.pressure_price > 0:
                close_price = current_data.close
                # 压力线价格需要除以100（数据库存储格式：1660代表16.60元）
                pressure_price_actual = prev_chance.pressure_price / 100.0
                distance_pct = (pressure_price_actual - close_price) / close_price * 100
                
                logger.info(f"[临近压力位滞涨-距离检查] {stock_code} {date_str} 股价{close_price:.2f}, 压力线{pressure_price_actual:.2f}, 距离{distance_pct:.2f}%, 赔率{day_win_ratio_score:.1f}, 距离阈值{distance_threshold}%")
                
                # 如果不在0%-阈值%的范围内，不触发插件
                if not (0 < distance_pct < distance_threshold):
                    logger.debug(f"[临近压力位滞涨] {stock_code} {date_str} 股价{close_price:.2f}距离压力线{pressure_price_actual:.2f}的距离{distance_pct:.2f}%不在0%-{distance_threshold}%范围内")
                    return RPointPluginResult("临近压力位滞涨", False, "")
            else:
                # 没有压力线数据，不触发插件
                logger.debug(f"[临近压力位滞涨] {stock_code} {date_str} 前一交易日无压力线数据")
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 检查上一个C点日的开盘价是否低于当日收盘价
            if c_point_date:
                c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else c_point_date
                c_data = self._daily_cache.get(c_date_str)
                if not c_data:
                    c_data = self.daily_repo.find_by_date(stock_code, c_date_str)
                
                # 如果有C点数据，检查C点日开盘价是否低于当日收盘价
                if c_data:
                    # C点日开盘价必须低于当日收盘价，否则不发R
                    if c_data.open >= current_data.close:
                        logger.debug(f"[临近压力位滞涨] {stock_code} {date_str} C点日开盘价{c_data.open:.2f}>=当日收盘价{current_data.close:.2f}，不发R")
                        return RPointPluginResult("临近压力位滞涨", False, "")
            
            # === 条件1: 放量 + 特定K线 ===
            is_volume_xyzh = self._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            
            logger.info(f"[临近压力位滞涨-条件1] {stock_code} {date_str} 成交量类型:{current_chance.volume_type}, 是否放量XYZH:{is_volume_xyzh}")
            
            if is_volume_xyzh:
                # 检查K线形态，返回所有命中的形态
                matched_patterns = self._check_bearish_kline_patterns(current_data, stock_code)
                
                logger.info(f"[临近压力位滞涨-条件1] {stock_code} {date_str} 命中K线形态:{matched_patterns}")
                
                if matched_patterns:
                    pattern_desc = "、".join(matched_patterns)
                    # 计算振幅
                    amplitude = 0
                    if current_data.pre_close and current_data.pre_close > 0:
                        amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                    
                    # 计算压力线距离
                    close_price = current_data.close
                    pressure_price_actual = prev_chance.pressure_price / 100.0
                    distance_pct = (pressure_price_actual - close_price) / close_price * 100
                    
                    # 如果有C点数据，在原因中说明C点开盘价
                    c_info = ""
                    if c_point_date and c_data:
                        c_info = f"+C点日开盘{c_data.open:.2f}<当日收盘{current_data.close:.2f}"
                    
                    return RPointPluginResult(
                        "临近压力位滞涨",
                        True,
                        f"条件1: 距压力位近(股性:{stock_nature},前日赔率{day_win_ratio_score:.1f}<{pressure_threshold},股价{close_price:.2f}距压力线{pressure_price_actual:.2f}仅{distance_pct:.2f}%)+放量+空头K线({pattern_desc},振幅{amplitude:.2f}%){c_info}"
                    )
            
            # === 条件2: 前3日无AXYZ放量 + 空头组合（仅熊市生效）===
            market_type = self.config_service.get_market_type()
            
            # 条件2仅在熊市生效
            if market_type == 'bear':
                prev_dates = self._get_previous_trading_dates_from_cache(date_str)
                if len(prev_dates) >= 3:
                    has_good_volume = False
                    for prev_date in prev_dates[:3]:
                        prev_chance = self._daily_chance_cache.get(prev_date)
                        if not prev_chance:
                            prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date)
                        if prev_chance:
                            if self._check_volume_type(prev_chance, ['A', 'X', 'Y', 'Z']):
                                has_good_volume = True
                                break
                    
                    if not has_good_volume:
                        # 检查当日是否有空头组合，并获取具体组合名称
                        if current_chance.bearish_pattern and len(current_chance.bearish_pattern.strip()) > 0:
                            bearish_patterns = current_chance.bearish_pattern.strip()
                            
                            # 计算压力线距离
                            close_price = current_data.close
                            pressure_price_actual = prev_chance.pressure_price / 100.0
                            distance_pct = (pressure_price_actual - close_price) / close_price * 100
                            
                            # 如果有C点数据，在原因中说明C点开盘价
                            c_info = ""
                            if c_point_date and c_data:
                                c_info = f"+C点日开盘{c_data.open:.2f}<当日收盘{current_data.close:.2f}"
                            
                            return RPointPluginResult(
                                "临近压力位滞涨",
                                True,
                                f"条件2(熊市): 距压力位近(股性:{stock_nature},前日赔率{day_win_ratio_score:.1f}<{pressure_threshold},股价{close_price:.2f}距压力线{pressure_price_actual:.2f}仅{distance_pct:.2f}%)+前3日无AXYZ放量+空头组合({bearish_patterns}){c_info}"
                            )
            
            return RPointPluginResult("临近压力位滞涨", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-临近压力位滞涨检查失败: {e}")
            return RPointPluginResult("临近压力位滞涨", False, "")
    
    def _check_fundamental_negative(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件3: 基本面突发利空
        
        条件: 一字跌停/T字跌停
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("基本面突发利空", False, "")
            
            # 判断是否跌停
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            limit_threshold = -9.9 if is_main_board else -19.8
            
            if current_data.pre_close and current_data.pre_close > 0:
                change_pct = (current_data.close - current_data.pre_close) / current_data.pre_close * 100
                
                if change_pct <= limit_threshold:
                    # 判断是否一字跌停（开=高=低=收）
                    is_one_line = (current_data.open == current_data.high == 
                                  current_data.low == current_data.close)
                    
                    # 判断是否T字跌停（开=低=收，且有上影线）
                    is_t_line = (current_data.open == current_data.low == current_data.close and 
                                current_data.high > current_data.close)
                    
                    if is_one_line or is_t_line:
                        limit_type = "一字跌停" if is_one_line else "T字跌停"
                        return RPointPluginResult(
                            "基本面突发利空",
                            True,
                            f"{limit_type}(跌幅{change_pct:.2f}%)"
                        )
            
            return RPointPluginResult("基本面突发利空", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-基本面突发利空检查失败: {e}")
            return RPointPluginResult("基本面突发利空", False, "")
    
    def _check_weak_breakout(self, stock_code: str, date: datetime, c_point_date: datetime) -> RPointPluginResult:
        """
        插件4: 上冲乏力
        
        条件: 
        - 从发C日起累计涨幅>15% 
        - 前一交易日日线赔率得分：短线<15分、波段<12分、中长线<10分（且不等于0）
        - 当前股价距离压力线：0% < (压力线-股价)/股价 < 8%
        - 压力线价格从数据库读取后需除以100（数据库存储格式：1660代表16.60元）
        - 前日涨幅>6%/8% 
        - 今日放量(AXYZH) 
        - 特定K线
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else c_point_date
            
            # 判断主板还是非主板
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            
            # 获取C点日期的数据
            c_data = self._daily_cache.get(c_date_str)
            if not c_data:
                c_data = self.daily_repo.find_by_date(stock_code, c_date_str)
            if not c_data:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 计算从C点到今日的累计涨幅
            cumulative_gain = ((current_data.close - c_data.close) / c_data.close * 100) if c_data.close else 0
            
            if cumulative_gain <= 15:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 获取当日daily_chance（用于获取股性和成交量类型）
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 获取股性
            stock_nature = current_chance.stock_nature or "波段"  # 默认波段
            
            # 获取前一交易日数据，使用前一交易日的赔率得分
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 1:
                return RPointPluginResult("上冲乏力", False, "")
            
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查前一交易日的赔率（根据股性判断）
            # 要求：赔率得分不等于0，且小于阈值
            day_win_ratio_score = prev_chance.day_win_ratio_score or 0
            win_ratio_threshold = self._get_win_ratio_threshold_for_weak_breakout(stock_nature)
            
            if not (0 < day_win_ratio_score < win_ratio_threshold):
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查当前股价距离压力线的距离
            # 要求：0% < (压力线-股价)/股价 < 8%
            if prev_chance.pressure_price and prev_chance.pressure_price > 0:
                close_price = current_data.close
                # 压力线价格需要除以100（数据库存储格式：1660代表16.60元）
                pressure_price_actual = prev_chance.pressure_price / 100.0
                distance_pct = (pressure_price_actual - close_price) / close_price * 100
                
                # 如果不在0%-8%的范围内，不触发插件
                if not (0 < distance_pct < 8):
                    logger.debug(f"[上冲乏力] {stock_code} {date_str} 股价{close_price:.2f}距离压力线{pressure_price_actual:.2f}的距离{distance_pct:.2f}%不在0%-8%范围内")
                    return RPointPluginResult("上冲乏力", False, "")
            else:
                # 没有压力线数据，不触发插件
                logger.debug(f"[上冲乏力] {stock_code} {date_str} 前一交易日无压力线数据")
                return RPointPluginResult("上冲乏力", False, "")
            
            # 获取前一日的K线数据（用于检查涨幅）
            yesterday_data = self._daily_cache.get(prev_date_str)
            if not yesterday_data:
                yesterday_data = self.daily_repo.find_by_date(stock_code, prev_date_str)
            if not yesterday_data:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查前一日涨幅
            yesterday_gain_threshold = 6 if is_main_board else 8
            yesterday_change = ((yesterday_data.close - yesterday_data.pre_close) / yesterday_data.pre_close * 100) if yesterday_data.pre_close else 0
            
            if yesterday_change < yesterday_gain_threshold:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查今日是否放量(AXYZH)
            is_volume = self._check_volume_type(current_chance, ['A', 'X', 'Y', 'Z', 'H'])
            if not is_volume:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查今日K线形态
            matched_patterns = self._check_bearish_kline_patterns(current_data, stock_code)
            
            if matched_patterns:
                pattern_desc = "、".join(matched_patterns)
                # 计算振幅
                amplitude = 0
                if current_data.pre_close and current_data.pre_close > 0:
                    amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
                
                # 计算压力线距离
                close_price = current_data.close
                pressure_price_actual = prev_chance.pressure_price / 100.0
                distance_pct = (pressure_price_actual - close_price) / close_price * 100
                
                return RPointPluginResult(
                    "上冲乏力",
                    True,
                    f"从C点涨幅{cumulative_gain:.2f}%+前日赔率(股性:{stock_nature},{day_win_ratio_score:.1f}<{win_ratio_threshold},股价{close_price:.2f}距压力线{pressure_price_actual:.2f}仅{distance_pct:.2f}%)+昨日涨{yesterday_change:.2f}%+今日放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                )
            
            return RPointPluginResult("上冲乏力", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-上冲乏力检查失败: {e}")
            return RPointPluginResult("上冲乏力", False, "")
    
    # ========== 辅助方法 ==========
    
    def _get_previous_trading_dates_from_cache(self, current_date_str: str) -> List[str]:
        """从缓存中获取前N个交易日的日期列表"""
        try:
            all_dates = sorted(self._daily_cache.keys(), reverse=True)
            result = []
            for date_str in all_dates:
                if date_str < current_date_str:
                    result.append(date_str)
            return result
        except Exception as e:
            logger.error(f"从缓存获取前N个交易日失败: {e}")
            return []
    
    def _check_high_position_r(self, stock_code: str, date: datetime, ma_data: dict, 
                               macd_data: dict, current_index: int) -> RPointPluginResult:
        """
        插件6: 高位发R
        
        条件:
        1. 均线多头排列判断：
           - 当前是多头排列（5日>10日>20日>30日>60日），或
           - 前3个交易日出现过多头排列但当前不是多头排列
        2. 从当前往前20个交易日的最低价涨幅 > 8%
        3. 当前股价 > 10日均线价格（确认目前是短期高点）
        4. 目前股价跌破前一日支撑位
        5. 当天MACD出现死叉，或已经出现死叉（之前5个交易日内出现死叉也算）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("高位发R", False, "")
            
            current_price = current_data.close
            
            # === 条件1: 均线多头排列（当前或前3个交易日出现过）===
            # 检查数据完整性
            if current_index < 0 or current_index >= len(ma_data.get('ma5', [])):
                return RPointPluginResult("高位发R", False, "")
            
            # 检查当前和前3个交易日是否出现过多头排列
            bullish_alignment_info = None
            checked_indices = []
            
            # 检查范围：当前及前3个交易日
            for check_idx in range(current_index, max(-1, current_index - 4), -1):
                if check_idx < 0:
                    continue
                
                ma5 = ma_data.get('ma5', [])[check_idx] if ma_data.get('ma5') else None
                ma10 = ma_data.get('ma10', [])[check_idx] if ma_data.get('ma10') else None
                ma20 = ma_data.get('ma20', [])[check_idx] if ma_data.get('ma20') else None
                ma30 = ma_data.get('ma30', [])[check_idx] if ma_data.get('ma30') else None
                ma60 = ma_data.get('ma60', [])[check_idx] if ma_data.get('ma60') else None
                
                # 跳过数据不完整的索引
                if None in [ma5, ma10, ma20, ma30, ma60]:
                    continue
                
                checked_indices.append(check_idx)
                
                # 检查是否多头排列
                if ma5 > ma10 > ma20 > ma30 > ma60:
                    is_current = (check_idx == current_index)
                    bullish_alignment_info = {
                        'index': check_idx,
                        'is_current': is_current,
                        'ma5': ma5,
                        'ma10': ma10,
                        'ma20': ma20,
                        'ma30': ma30,
                        'ma60': ma60
                    }
                    break
            
            # 如果当前和前3个交易日都没有多头排列，不触发
            if not bullish_alignment_info:
                return RPointPluginResult("高位发R", False, "")
            
            # 获取当前均线值（用于后续条件2判断）
            ma5_current = ma_data.get('ma5', [])[current_index] if ma_data.get('ma5') else None
            ma10_current = ma_data.get('ma10', [])[current_index] if ma_data.get('ma10') else None
            ma20_current = ma_data.get('ma20', [])[current_index] if ma_data.get('ma20') else None
            ma30_current = ma_data.get('ma30', [])[current_index] if ma_data.get('ma30') else None
            ma60_current = ma_data.get('ma60', [])[current_index] if ma_data.get('ma60') else None
            
            if None in [ma10_current]:
                return RPointPluginResult("高位发R", False, "")
            
            # === 条件2: 从当前往前20个交易日的最低价涨幅 > 配置阈值 ===
            # 从配置中获取涨幅阈值（默认8%）
            gain_threshold = self.config_service.get_high_position_gain_threshold()
            
            # 获取前20个交易日的数据
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 20:
                return RPointPluginResult("高位发R", False, "")
            
            # 找出前20个交易日的最低价
            lowest_price = None
            lowest_date = None
            
            for prev_date in prev_dates[:20]:
                prev_data = self._daily_cache.get(prev_date)
                if not prev_data:
                    prev_data = self.daily_repo.find_by_date(stock_code, prev_date)
                if prev_data and prev_data.low:
                    if lowest_price is None or prev_data.low < lowest_price:
                        lowest_price = prev_data.low
                        lowest_date = prev_date
            
            # 检查是否找到最低价
            if lowest_price is None or lowest_price <= 0:
                return RPointPluginResult("高位发R", False, "")
            
            # 计算涨幅
            gain_from_lowest = ((current_price - lowest_price) / lowest_price) * 100
            
            # 涨幅必须大于阈值
            if gain_from_lowest <= gain_threshold:
                logger.debug(f"[高位发R] {stock_code} {date_str} 20日最低价{lowest_price:.2f}至当前{current_price:.2f}涨幅{gain_from_lowest:.2f}%不满足>{gain_threshold}%条件")
                return RPointPluginResult("高位发R", False, "")
            
            # === 条件3: 当前股价 > 10日均线（确认短期高点）===
            if current_price <= ma10_current:
                return RPointPluginResult("高位发R", False, "")
            
            # === 条件4: 跌破前一日支撑位 ===
            # 获取前一交易日
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if not prev_dates or len(prev_dates) < 1:
                return RPointPluginResult("高位发R", False, "")
            
            prev_date_str = prev_dates[0]
            
            # 获取前一日的daily_chance（支撑位）
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("高位发R", False, "")
            
            # 检查前一日是否有支撑位
            if not prev_chance.support_price or prev_chance.support_price <= 0:
                return RPointPluginResult("高位发R", False, "")
            
            # 支撑位需要除以100
            support_price_actual = prev_chance.support_price / 100.0
            
            # 跌破支撑位
            is_break_support = current_price < support_price_actual
            if not is_break_support:
                return RPointPluginResult("高位发R", False, "")
            
            # === 条件5: MACD死叉（当天或前5个交易日内）===
            dif_list = macd_data.get('dif', [])
            dea_list = macd_data.get('dea', [])
            
            if not dif_list or not dea_list or current_index >= len(dif_list):
                return RPointPluginResult("高位发R", False, "")
            
            # 检查当天及前5个交易日是否出现死叉
            death_cross_found = False
            death_cross_date = None
            
            # 检查范围：当天及前5天
            start_check_index = max(1, current_index - 5)
            for check_index in range(start_check_index, current_index + 1):
                if check_index <= 0:
                    continue
                
                curr_dif = dif_list[check_index]
                curr_dea = dea_list[check_index]
                prev_dif = dif_list[check_index - 1]
                prev_dea = dea_list[check_index - 1]
                
                if None in [curr_dif, curr_dea, prev_dif, prev_dea]:
                    continue
                
                # 死叉：前一天DIF>DEA，当天DIF<DEA
                if prev_dif > prev_dea and curr_dif < curr_dea:
                    death_cross_found = True
                    death_cross_date = check_index
                    break
                
                # 或者已经处于死叉状态（当天DIF<DEA）
                if check_index == current_index and curr_dif < curr_dea:
                    death_cross_found = True
                    death_cross_date = check_index
                    break
            
            if not death_cross_found:
                return RPointPluginResult("高位发R", False, "")
            
            # === 全部条件满足，触发高位发R ===
            # 构建多头排列描述
            ma_info = bullish_alignment_info
            if ma_info['is_current']:
                ma_desc = f"当前多头排列(MA5:{ma_info['ma5']:.2f}>MA10:{ma_info['ma10']:.2f}>MA20:{ma_info['ma20']:.2f}>MA30:{ma_info['ma30']:.2f}>MA60:{ma_info['ma60']:.2f})"
            else:
                ma_desc = f"前{current_index - ma_info['index']}日多头排列(MA5:{ma_info['ma5']:.2f}>MA10:{ma_info['ma10']:.2f}>MA20:{ma_info['ma20']:.2f}>MA30:{ma_info['ma30']:.2f}>MA60:{ma_info['ma60']:.2f})"
            
            reason = (f"{ma_desc}, "
                     f"20日最低价{lowest_price:.2f}({lowest_date})涨至{current_price:.2f}涨幅{gain_from_lowest:.2f}%, "
                     f"股价({current_price:.2f})>MA10({ma10_current:.2f}), "
                     f"跌破支撑({support_price_actual:.2f}), "
                     f"MACD死叉")
            
            logger.info(f"[高位发R触发] {stock_code} {date_str}: {reason}")
            return RPointPluginResult("高位发R", True, reason)
            
        except Exception as e:
            logger.error(f"插件6-高位发R检查异常: {e}")
            return RPointPluginResult("高位发R", False, "")
    
    def _check_box_breakdown(self, stock_code: str, date: datetime, macd_data: dict, 
                            current_index: int, kline_data: list) -> RPointPluginResult:
        """
        插件7: 箱体回踩被跌破
        
        条件:
        1. 从当前往前20个交易日找到最高价日X日，X日最高价距离当前价格 > 18%
        2. X日往前推22个交易日，X日应该是这23天的前30%高位区域（相对高点）
        3. X-22日到X日这23天，最低价到最高价的涨幅 >= 18%
        4. 当前股价跌破前一日支撑位
        5. MACD出现死叉（前5个交易日内）或已形成死叉且当前未出现金叉
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 需要至少42个交易日数据（20 + 22）
            if current_index < 42:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            current_price = current_data.close
            
            # === 条件1: 找X日（当前往前20天的最高价所在日）===
            x_day_high = 0
            x_day_index = -1
            
            for i in range(current_index - 19, current_index + 1):
                if kline_data[i].high > x_day_high:
                    x_day_high = kline_data[i].high
                    x_day_index = i
            
            if x_day_index < 0:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 检查X日最高价距离当前价格 > 18%
            drop_ratio = (x_day_high - current_price) / x_day_high
            if drop_ratio <= 0.18:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 条件2: X-22日到X日这23天，最低价到最高价的涨幅 >= 18% ===
            if x_day_index < 22:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 计算X-22到X日这23天的最低价和最高价
            box_start_index = x_day_index - 22
            box_lowest_price = None
            box_highest_price = None
            box_lowest_date = None
            box_highest_date = None
            
            for i in range(box_start_index, x_day_index + 1):
                # 找最低价
                if box_lowest_price is None or kline_data[i].low < box_lowest_price:
                    box_lowest_price = kline_data[i].low
                    box_lowest_date = kline_data[i].time.strftime('%Y-%m-%d')
                
                # 找最高价
                if box_highest_price is None or kline_data[i].high > box_highest_price:
                    box_highest_price = kline_data[i].high
                    box_highest_date = kline_data[i].time.strftime('%Y-%m-%d')
            
            # 检查数据有效性
            if box_lowest_price is None or box_highest_price is None or box_lowest_price <= 0:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 计算涨幅
            box_gain_ratio = (box_highest_price - box_lowest_price) / box_lowest_price
            
            # 涨幅必须 >= 18%
            if box_gain_ratio < 0.18:
                logger.debug(f"[箱体回踩] {stock_code} X-22至X日涨幅{box_gain_ratio*100:.2f}%不满足>=18%条件")
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 条件2补充: X日应该是这23天的前30%高位区域（相对高点）===
            # 计算X-22到X日这23天的所有最高价
            box_highs = [kline_data[i].high for i in range(box_start_index, x_day_index + 1)]
            
            # 排序找前30%分界线
            sorted_highs = sorted(box_highs, reverse=True)
            top_30_percent_count = max(1, int(len(sorted_highs) * 0.3))
            top_30_threshold = sorted_highs[top_30_percent_count - 1]
            
            # X日最高价应该在前30%高位区域
            if x_day_high < top_30_threshold:
                logger.debug(f"[箱体回踩] {stock_code} X日最高价{x_day_high:.2f}不在前30%高位区域(阈值{top_30_threshold:.2f})")
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 条件4: 跌破前一日支撑位 ===
            # 获取前一交易日
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if not prev_dates or len(prev_dates) < 1:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            prev_date_str = prev_dates[0]
            
            # 获取前一日的daily_chance（支撑位）
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 检查前一日是否有支撑位
            if not prev_chance.support_price or prev_chance.support_price <= 0:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 支撑位需要除以100
            support_price_actual = prev_chance.support_price / 100.0
            
            # 跌破支撑位
            is_break_support = current_price < support_price_actual
            if not is_break_support:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 条件5: MACD死叉（前5个交易日内出现死叉）或（已形成死叉且当前未出现金叉）===
            dif_list = macd_data.get('dif', [])
            dea_list = macd_data.get('dea', [])
            
            if not dif_list or not dea_list or current_index >= len(dif_list) or current_index < 1:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            curr_dif = dif_list[current_index]
            curr_dea = dea_list[current_index]
            prev_dif = dif_list[current_index - 1]
            prev_dea = dea_list[current_index - 1]
            
            if None in [curr_dif, curr_dea, prev_dif, prev_dea]:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 条件A：前5个交易日内出现死叉（从金叉转为死叉）
            death_cross_in_recent_5_days = False
            start_check_index = max(1, current_index - 5)
            
            for check_index in range(start_check_index, current_index + 1):
                if check_index <= 0:
                    continue
                
                check_dif = dif_list[check_index]
                check_dea = dea_list[check_index]
                check_prev_dif = dif_list[check_index - 1]
                check_prev_dea = dea_list[check_index - 1]
                
                if None in [check_dif, check_dea, check_prev_dif, check_prev_dea]:
                    continue
                
                # 死叉：前一天DIF>DEA，当天DIF<DEA（转换点）
                if check_prev_dif > check_prev_dea and check_dif < check_dea:
                    death_cross_in_recent_5_days = True
                    logger.debug(f"[箱体回踩] 在索引{check_index}发现死叉转换点")
                    break
            
            # 条件B：已形成死叉且当天未出现金叉
            is_currently_death_cross = curr_dif < curr_dea  # 当前处于死叉状态
            is_today_golden_cross = prev_dif < prev_dea and curr_dif > curr_dea  # 今天出现金叉
            already_death_cross_no_golden = is_currently_death_cross and not is_today_golden_cross
            
            # 条件A 或 条件B
            if not (death_cross_in_recent_5_days or already_death_cross_no_golden):
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 全部条件满足，触发箱体回踩被跌破 ===
            x_day_date = kline_data[x_day_index].time.strftime('%Y-%m-%d')
            reason = (f"X日({x_day_date})最高价{x_day_high:.2f}在23天前30%高位, "
                     f"X-22至X日最低价{box_lowest_price:.2f}({box_lowest_date})至最高价{box_highest_price:.2f}({box_highest_date})涨幅{box_gain_ratio*100:.1f}%, "
                     f"当前({current_price:.2f})较X日跌破{drop_ratio*100:.1f}%, "
                     f"跌破支撑({support_price_actual:.2f}), "
                     f"MACD死叉")
            
            logger.info(f"[箱体回踩被跌破触发] {stock_code} {date_str}: X日={x_day_date}, "
                       f"X日高{x_day_high:.2f}在前30%高位(阈值{top_30_threshold:.2f}), 当前{current_price:.2f}, 跌幅{drop_ratio*100:.1f}%, "
                       f"箱体涨幅{box_gain_ratio*100:.1f}%")
            return RPointPluginResult("箱体回踩被跌破", True, reason)
            
        except Exception as e:
            logger.error(f"插件7-箱体回踩被跌破检查异常: {e}")
            return RPointPluginResult("箱体回踩被跌破", False, "")
    
    def _check_volume_type(self, daily_chance, target_types: List[str]) -> bool:
        """检查成交量类型是否在目标类型中"""
        if not daily_chance or not daily_chance.volume_type:
            return False
        volume_types = [t.strip() for t in daily_chance.volume_type.split(',')]
        return any(t in target_types for t in volume_types)
    
    def _check_bearish_pattern(self, daily_chance) -> bool:
        """检查是否有空头组合"""
        if not daily_chance or not daily_chance.bearish_pattern:
            return False
        return len(daily_chance.bearish_pattern.strip()) > 0
    
    def _get_pressure_threshold(self, stock_nature: str) -> float:
        """
        根据股性获取压力位阈值（用于临近压力位滞涨）
        
        Args:
            stock_nature: 股性（短线、波段、中长线）
            
        Returns:
            赔率得分阈值
        """
        thresholds = {
            "短线": 12.0,
            "波段": 10.0,
            "中长线": 8.0
        }
        return thresholds.get(stock_nature, 10.0)  # 默认波段
    
    def _get_win_ratio_threshold_for_weak_breakout(self, stock_nature: str) -> float:
        """
        根据股性获取赔率阈值（用于上冲乏力）
        
        Args:
            stock_nature: 股性（短线、波段、中长线）
            
        Returns:
            赔率得分阈值
        """
        thresholds = {
            "短线": 15.0,
            "波段": 12.0,
            "中长线": 10.0
        }
        return thresholds.get(stock_nature, 12.0)  # 默认波段
    
    def _check_bearish_kline_patterns(self, daily_data, stock_code: str = None) -> List[str]:
        """
        检查所有空头K线形态，返回命中的形态列表
        
        Args:
            daily_data: 日K线数据
            stock_code: 股票代码（用于判断主板/非主板）
        
        Returns:
            命中的K线形态列表，如 ["冲高回落阳线", "高开低走"]
        """
        if not daily_data or not daily_data.pre_close or daily_data.pre_close == 0:
            return []
        
        matched_patterns = []
        
        # 判断主板还是非主板
        is_main_board = True
        if stock_code:
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        
        # 计算ABC
        O = daily_data.open
        C = daily_data.close
        H = daily_data.high
        L = daily_data.low
        prev_close = daily_data.pre_close
        
        # A: 上影线 = 最高价 - max(开盘价, 收盘价)
        A = H - max(O, C)
        # B: 实体 = abs(收盘价 - 开盘价)
        B = abs(C - O)
        # C: 下影线 = min(开盘价, 收盘价) - 最低价
        C_shadow = min(O, C) - L
        
        # 1. 冲高回落阳线（需要振幅>6%/8%）
        if self._check_bullish_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阳线")
        
        # 2. 冲高回落阴线（需要振幅>6%/8%）
        if self._check_bearish_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阴线")
        
        # 3. 冲高回落阳十字星（需要振幅>6%/8%）
        if self._check_bullish_doji_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阳十字星")
        
        # 4. 冲高回落阴十字星（需要振幅>6%/8%）
        if self._check_bearish_doji_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阴十字星")
        
        # 5. 高开低走（需要振幅>6%/8%）
        if self._check_high_open_low_close_new(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("高开低走")
        
        # 6. 阴线跌幅>3%（相对昨收）- 不需要振幅条件
        if self._check_bearish_line_3pct_new(O, C, prev_close):
            matched_patterns.append("阴线跌幅>3%")
        
        return matched_patterns
    
    def _check_bullish_high_fallback(self, A: float, B: float, C: float, O: float, close: float, 
                                     H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        冲高回落阳线
        振幅 > 6%（主板）或 8%（非主板）
        A >= 2C
        A >= 2B
        1% < B/最低价 < 3.3%
        开盘价 < 收盘价
        """
        if O >= close:  # 不是阳线
            return False
        if L == 0 or prev_close == 0:
            return False
        
        # 检查振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        if amplitude <= amplitude_threshold:
            return False
        
        b_ratio = (B / L) * 100
        
        return (A >= 2 * C and 
                A >= 2 * B and 
                1 < b_ratio < 3.3)
    
    def _check_bearish_high_fallback(self, A: float, B: float, C: float, O: float, close: float,
                                     H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        冲高回落阴线
        振幅 > 6%（主板）或 8%（非主板）
        A >= 2C
        A >= 2B
        1% < B/最低价 < 3.3%
        开盘价 > 收盘价
        """
        if O <= close:  # 不是阴线
            return False
        if L == 0 or prev_close == 0:
            return False
        
        # 检查振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        if amplitude <= amplitude_threshold:
            return False
        
        b_ratio = (B / L) * 100
        
        return (A >= 2 * C and 
                A >= 2 * B and 
                1 < b_ratio < 3.3)
    
    def _check_bullish_doji_high_fallback(self, A: float, B: float, C: float, O: float, close: float,
                                          H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        冲高回落阳十字星
        振幅 > 6%（主板）或 8%（非主板）
        开盘价 < 收盘价
        B/最低价 < 2%
        C > 0
        A > 2C
        """
        if O >= close:  # 不是阳线
            return False
        if L == 0 or C == 0 or prev_close == 0:
            return False
        
        # 检查振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        if amplitude <= amplitude_threshold:
            return False
        
        b_ratio = (B / L) * 100
        
        return (b_ratio < 2 and 
                A > 2 * C)
    
    def _check_bearish_doji_high_fallback(self, A: float, B: float, C: float, O: float, close: float,
                                          H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        冲高回落阴十字星
        振幅 > 6%（主板）或 8%（非主板）
        开盘价 > 收盘价
        B/最低价 < 2%
        C > 0
        A > 2C
        """
        if O <= close:  # 不是阴线
            return False
        if L == 0 or C == 0 or prev_close == 0:
            return False
        
        # 检查振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        if amplitude <= amplitude_threshold:
            return False
        
        b_ratio = (B / L) * 100
        
        return (b_ratio < 2 and 
                A > 2 * C)
    
    def _check_high_open_low_close_new(self, A: float, B: float, C: float, O: float, close: float,
                                       H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        高开低走
        振幅 > 6%（主板）或 8%（非主板）
        开盘价 > 收盘价
        A = 0
        C < 2B
        """
        if O <= close:  # 不是阴线
            return False
        if prev_close == 0:
            return False
        
        # 检查振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        if amplitude <= amplitude_threshold:
            return False
        
        return (A == 0 and C < 2 * B)
    
    def _check_bearish_line_3pct_new(self, O: float, close: float, prev_close: float) -> bool:
        """
        阴线跌幅>3%（相对昨收）
        """
        if prev_close == 0:
            return False
        
        change_pct = ((close - prev_close) / prev_close) * 100
        
        return change_pct < -3
    
    def _check_break_support(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件5: 跌破支撑位
        
        条件: 日收盘价 < 前一日支撑位 + 当日放量(XYZ)
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 获取当日daily_chance（成交量类型）
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 获取前一交易日
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if not prev_dates or len(prev_dates) < 1:
                return RPointPluginResult("跌破支撑位", False, "")
            
            prev_date_str = prev_dates[0]
            
            # 获取前一日的daily_chance（支撑位）
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 检查前一日是否有支撑位
            if not prev_chance.support_price or prev_chance.support_price <= 0:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 支撑位需要除以100（数据库存储的是整数形式，如1463代表14.63元）
            support_price_actual = prev_chance.support_price / 100.0
            
            # 条件1: 当日收盘价 < 前一日支撑位
            is_break_support = current_data.close < support_price_actual
            
            if not is_break_support:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 条件2: 当日成交量是XYZ（放量）
            is_volume_xyz = self._check_volume_type(current_chance, ['X', 'Y', 'Z'])
            
            if not is_volume_xyz:
                return RPointPluginResult("跌破支撑位", False, "")
            
            # 计算跌幅
            break_ratio = ((current_data.close - support_price_actual) / support_price_actual) * 100
            
            return RPointPluginResult(
                "跌破支撑位",
                True,
                f"收盘价{current_data.close:.2f}<前日支撑位{support_price_actual:.2f}(跌破{abs(break_ratio):.2f}%)+放量({current_chance.volume_type})"
            )
            
        except Exception as e:
            logger.error(f"R点插件-跌破支撑位检查失败: {e}")
            return RPointPluginResult("跌破支撑位", False, "")

