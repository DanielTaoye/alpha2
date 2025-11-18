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
    
    def check_r_point(self, stock_code: str, date: datetime, c_point_date: Optional[datetime] = None) -> Tuple[bool, List[RPointPluginResult]]:
        """
        检查是否触发R点（卖出信号）
        
        Args:
            stock_code: 股票代码
            date: 检查日期
            c_point_date: C点触发日期（用于"上冲乏力"判断）
            
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
        plugin2 = self._check_pressure_stagnation(stock_code, date)
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
            is_bearish_divergence = self._check_bearish_divergence_kline(current_data, is_main_board)
            is_bearish_line = self._check_bearish_line_above_threshold(current_data, is_main_board)
            has_bearish_pattern = self._check_bearish_pattern(current_chance)
            
            # 调试日志
            logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 基础检查: volume_type={current_chance.volume_type}, "
                        f"is_volume_xyh={is_volume_xyh}, is_volume_xyzh={is_volume_xyzh}, "
                        f"is_bearish_divergence={is_bearish_divergence}, is_bearish_line={is_bearish_line}, "
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
                            f"is_volume_xyh={is_volume_xyh}, is_bearish_divergence={is_bearish_divergence}, is_bearish_line={is_bearish_line}")
                if (is_volume_xyh and is_bearish_divergence) or (is_volume_xyh and is_bearish_line):
                    return RPointPluginResult(
                        "乖离率偏离",
                        True,
                        f"条件1: 连续{consecutive_limits}个涨停+放量+空头K线"
                    )
            
            # === 条件2: 前3日累计涨幅过大 ===
            if len(change_pcts) >= 3:
                cum_3days = sum(change_pcts[:3])
                threshold_3days = 15 if is_main_board else 20
                if cum_3days > threshold_3days:
                    logger.debug(f"[R点-乖离率偏离-条件2] {stock_code} {date_str} 前3日涨幅{cum_3days:.2f}%>{threshold_3days}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_divergence={is_bearish_divergence}, is_bearish_line={is_bearish_line}")
                    if (is_volume_xyh and is_bearish_divergence) or (is_volume_xyh and is_bearish_line):
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件2: 前3日涨幅{cum_3days:.2f}%+放量+空头K线"
                        )
            
            # === 条件3: 前5日累计涨幅过大 ===
            if len(change_pcts) >= 5:
                cum_5days = sum(change_pcts[:5])
                threshold_5days = 20 if is_main_board else 25
                if cum_5days > threshold_5days:
                    logger.debug(f"[R点-乖离率偏离-条件3] {stock_code} {date_str} 前5日涨幅{cum_5days:.2f}%>{threshold_5days}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_divergence={is_bearish_divergence}, is_bearish_line={is_bearish_line}")
                    if (is_volume_xyh and is_bearish_divergence) or (is_volume_xyh and is_bearish_line):
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件3: 前5日涨幅{cum_5days:.2f}%+放量+空头K线"
                        )
            
            # === 条件4: 连续5连阳+涨幅过大 ===
            if len(prev_data_list) >= 5:
                all_bullish = all(prev_data_list[i].close >= prev_data_list[i].open for i in range(5))
                cum_5days_yang = sum(change_pcts[:5])
                threshold_yang = 20 if is_main_board else 25
                if all_bullish and cum_5days_yang > threshold_yang:
                    logger.debug(f"[R点-乖离率偏离-条件4] {stock_code} {date_str} 5连阳+涨幅{cum_5days_yang:.2f}%>{threshold_yang}%, "
                                f"is_volume_xyh={is_volume_xyh}, is_bearish_divergence={is_bearish_divergence}, is_bearish_line={is_bearish_line}")
                    if (is_volume_xyh and is_bearish_divergence) or (is_volume_xyh and is_bearish_line):
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件4: 连续5连阳+涨幅{cum_5days_yang:.2f}%+放量+空头K线"
                        )
            
            # === 条件5: 前15日累计涨幅>50% ===
            if len(change_pcts) >= 15:
                cum_15days = sum(change_pcts[:15])
                if cum_15days > 50:
                    logger.debug(f"[R点-乖离率偏离-条件5] {stock_code} {date_str} 前15日涨幅{cum_15days:.2f}%>50%, "
                                f"is_volume_xyzh={is_volume_xyzh}, is_bearish_divergence={is_bearish_divergence}, has_bearish_pattern={has_bearish_pattern}")
                    if is_volume_xyzh and (is_bearish_divergence or has_bearish_pattern):
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件5: 前15日涨幅{cum_15days:.2f}%+放量+空头信号"
                        )
            
            # === 条件6: 前20日累计涨幅>50% ===
            if len(change_pcts) >= 20:
                cum_20days = sum(change_pcts[:20])
                if cum_20days > 50:
                    logger.debug(f"[R点-乖离率偏离-条件6] {stock_code} {date_str} 前20日涨幅{cum_20days:.2f}%>50%, "
                                f"is_volume_xyzh={is_volume_xyzh}, is_bearish_divergence={is_bearish_divergence}, has_bearish_pattern={has_bearish_pattern}")
                    if is_volume_xyzh and (is_bearish_divergence or has_bearish_pattern):
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件6: 前20日涨幅{cum_20days:.2f}%+放量+空头信号"
                        )
            
            return RPointPluginResult("乖离率偏离", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-乖离率偏离检查失败: {e}")
            return RPointPluginResult("乖离率偏离", False, "")
    
    def _check_pressure_stagnation(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件2: 临近压力位滞涨
        
        条件1: 距离压力位近(<15%) + 放量(XYZH) + 特定K线
        条件2: 距离压力位近(<15%) + 前3日无AXYZ放量 + 空头组合
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
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 获取当日daily_chance
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 计算日线赔率（距离压力位的空间）
            day_win_ratio_score = current_chance.day_win_ratio_score or 0
            # 赔率分<6分视为距离压力位较近
            is_near_pressure = day_win_ratio_score < 6
            
            if not is_near_pressure:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # === 条件1: 放量 + 特定K线 ===
            is_volume_xyzh = self._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            
            if is_volume_xyzh:
                # 检查K线形态
                is_bearish_divergence = self._check_bearish_divergence_kline(current_data, is_main_board)
                is_bearish_doji = self._check_bearish_doji(current_data, is_main_board)
                is_high_open_low_close = self._check_high_open_low_close(current_data, is_main_board)
                is_bearish_line_3pct = self._check_bearish_line_above_threshold(current_data, is_main_board, 3)
                
                if is_bearish_divergence or is_bearish_doji or is_high_open_low_close or is_bearish_line_3pct:
                    return RPointPluginResult(
                        "临近压力位滞涨",
                        True,
                        f"条件1: 距压力位近(赔率{day_win_ratio_score:.1f}<6)+放量+空头K线"
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
                        has_bearish_pattern = self._check_bearish_pattern(current_chance)
                        if has_bearish_pattern:
                            return RPointPluginResult(
                                "临近压力位滞涨",
                                True,
                                f"条件2(熊市): 距压力位近(赔率{day_win_ratio_score:.1f}<6)+前3日无放量+空头组合"
                            )
            
            return RPointPluginResult("临近压力位滞涨", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-临近压力位滞涨检查失败: {e}")
            return RPointPluginResult("临近压力位滞涨", False, "")
    
    def _check_fundamental_negative(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件3: 基本面突发利空
        
        条件: 一字跌停/T字跌停 (TODO: 需要接入AI检测利空)
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
                        # TODO: 这里应该接入AI检测基本面利空
                        return RPointPluginResult(
                            "基本面突发利空",
                            True,
                            f"{limit_type}(需AI确认基本面利空)"
                        )
            
            return RPointPluginResult("基本面突发利空", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-基本面突发利空检查失败: {e}")
            return RPointPluginResult("基本面突发利空", False, "")
    
    def _check_weak_breakout(self, stock_code: str, date: datetime, c_point_date: datetime) -> RPointPluginResult:
        """
        插件4: 上冲乏力
        
        条件: 从发C日起累计涨幅>15% + 今日赔率<25% + 前日涨幅>6%/8% + 今日放量 + 特定K线
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
            
            # 获取当日daily_chance
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查今日赔率
            day_win_ratio_score = current_chance.day_win_ratio_score or 0
            if day_win_ratio_score >= 10:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 获取前一日数据
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 1:
                return RPointPluginResult("上冲乏力", False, "")
            
            yesterday_data = self._daily_cache.get(prev_dates[0])
            if not yesterday_data:
                yesterday_data = self.daily_repo.find_by_date(stock_code, prev_dates[0])
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
            is_bearish_divergence = self._check_bearish_divergence_kline(current_data, is_main_board)
            is_bearish_doji = self._check_bearish_doji(current_data, is_main_board)
            is_high_open_low_close = self._check_high_open_low_close(current_data, is_main_board)
            is_bearish_line_3pct = self._check_bearish_line_above_threshold(current_data, is_main_board, 3)
            
            if is_bearish_divergence or is_bearish_doji or is_high_open_low_close or is_bearish_line_3pct:
                return RPointPluginResult(
                    "上冲乏力",
                    True,
                    f"从C点涨幅{cumulative_gain:.2f}%+赔率{day_win_ratio_score:.1f}+昨日涨{yesterday_change:.2f}%+今日放量+空头K线"
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
    
    def _check_bearish_divergence_kline(self, daily_data, is_main_board: bool) -> bool:
        """
        检查是否为空头分歧K线（冲高回落）
        振幅>6%/8% 且有明显上影线
        """
        if not daily_data or not daily_data.pre_close or daily_data.pre_close == 0:
            return False
        
        amplitude_threshold = 6 if is_main_board else 8
        amplitude = ((daily_data.high - daily_data.low) / daily_data.pre_close * 100)
        
        if amplitude < amplitude_threshold:
            return False
        
        # 计算上影线比例
        body_high = max(daily_data.open, daily_data.close)
        upper_shadow = daily_data.high - body_high
        upper_shadow_ratio = (upper_shadow / (daily_data.high - daily_data.low)) if (daily_data.high - daily_data.low) > 0 else 0
        
        # 上影线占比>30%视为冲高回落
        return upper_shadow_ratio > 0.3
    
    def _check_bearish_doji(self, daily_data, is_main_board: bool) -> bool:
        """
        检查是否为空头十字星
        振幅>6%/8% 且实体很小
        """
        if not daily_data or not daily_data.pre_close or daily_data.pre_close == 0:
            return False
        
        amplitude_threshold = 6 if is_main_board else 8
        amplitude = ((daily_data.high - daily_data.low) / daily_data.pre_close * 100)
        
        if amplitude < amplitude_threshold:
            return False
        
        # 实体占比<1%视为十字星
        body = abs(daily_data.close - daily_data.open)
        body_ratio = (body / daily_data.close * 100) if daily_data.close else 0
        
        return body_ratio < 1
    
    def _check_high_open_low_close(self, daily_data, is_main_board: bool) -> bool:
        """
        检查是否为高开低走
        振幅>6%/8% 且开盘价接近最高价、收盘价接近最低价
        """
        if not daily_data or not daily_data.pre_close or daily_data.pre_close == 0:
            return False
        
        amplitude_threshold = 6 if is_main_board else 8
        amplitude = ((daily_data.high - daily_data.low) / daily_data.pre_close * 100)
        
        if amplitude < amplitude_threshold:
            return False
        
        # 判断高开低走：开盘价在高位，收盘价在低位
        range_val = daily_data.high - daily_data.low
        if range_val == 0:
            return False
        
        open_position = (daily_data.open - daily_data.low) / range_val
        close_position = (daily_data.close - daily_data.low) / range_val
        
        # 开盘价在上70%，收盘价在下30%
        return open_position > 0.7 and close_position < 0.3
    
    def _check_bearish_line_above_threshold(self, daily_data, is_main_board: bool, threshold: float = 3) -> bool:
        """
        检查是否为阴线且跌幅超过阈值
        
        Args:
            threshold: 跌幅阈值（3%或5%）
        """
        if not daily_data or not daily_data.pre_close or daily_data.pre_close == 0:
            return False
        
        # 判断是否阴线
        if daily_data.close >= daily_data.open:
            return False
        
        # 计算跌幅
        change_pct = ((daily_data.close - daily_data.pre_close) / daily_data.pre_close * 100)
        
        # 阈值根据主板调整（如果需要）
        actual_threshold = threshold if is_main_board else (threshold * 5 / 3)
        
        return change_pct < -actual_threshold

