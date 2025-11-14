"""C点插件服务 - 优先级高于基础分数"""
from typing import Tuple, List, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CPointPluginResult:
    """插件结果"""
    def __init__(self, plugin_name: str, triggered: bool, score_adjustment: float, reason: str):
        self.plugin_name = plugin_name  # 插件名称
        self.triggered = triggered  # 是否触发
        self.score_adjustment = score_adjustment  # 分数调整（负数表示扣分）
        self.reason = reason  # 触发原因
    
    def to_dict(self):
        return {
            'pluginName': self.plugin_name,
            'triggered': self.triggered,
            'scoreAdjustment': self.score_adjustment,
            'reason': self.reason
        }


class CPointPluginService:
    """C点插件服务 - 计算层"""
    
    def __init__(self):
        """初始化插件服务"""
        from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
        from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
        self.daily_repo = DailyRepositoryImpl()
        self.daily_chance_repo = DailyChanceRepositoryImpl()
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
        logger.info(f"开始初始化插件缓存: {stock_code} {start_date} 至 {end_date}")
        
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
        
        logger.info(f"插件缓存初始化完成: daily={len(self._daily_cache)}条, daily_chance={len(self._daily_chance_cache)}条")
    
    def clear_cache(self):
        """清空缓存"""
        self._daily_cache = {}
        self._daily_chance_cache = {}
    
    def apply_plugins(self, stock_code: str, date: datetime, base_score: float) -> Tuple[float, List[CPointPluginResult]]:
        """
        应用所有插件，返回调整后的分数和触发的插件列表
        
        Args:
            stock_code: 股票代码
            date: 日期
            base_score: 基础分数（赔率分+胜率分）
            
        Returns:
            Tuple[final_score, triggered_plugins]
        """
        triggered_plugins = []
        adjusted_score = base_score
        
        # 插件1: 阴线检查（一票否决）
        plugin1 = self._check_bearish_line(stock_code, date)
        if plugin1.triggered:
            triggered_plugins.append(plugin1)
            logger.info(f"[插件-阴线] {stock_code} {date}: {plugin1.reason}")
            return 0, triggered_plugins  # 直接返回0分，不再检查其他插件
        
        # 插件2: 赔率高胜率低
        plugin2 = self._check_high_ratio_low_win(stock_code, date)
        if plugin2.triggered:
            triggered_plugins.append(plugin2)
            adjusted_score += plugin2.score_adjustment
            logger.info(f"[插件-赔率高胜率低] {stock_code} {date}: {plugin2.reason}, 扣分{abs(plugin2.score_adjustment)}")
        
        # 插件3: 风险K线
        plugin3 = self._check_risk_kline(stock_code, date)
        if plugin3.triggered:
            triggered_plugins.append(plugin3)
            logger.info(f"[插件-风险K线] {stock_code} {date}: {plugin3.reason}")
            return 0, triggered_plugins  # 一票否决
        
        # 插件4: 不追涨
        plugin4 = self._check_no_chase_high(stock_code, date)
        if plugin4.triggered:
            triggered_plugins.append(plugin4)
            adjusted_score += plugin4.score_adjustment
            logger.info(f"[插件-不追涨] {stock_code} {date}: {plugin4.reason}, 扣分{abs(plugin4.score_adjustment)}")
        
        # 插件5: 急跌抢反弹（直接发C）
        plugin5 = self._check_sharp_drop_rebound(stock_code, date)
        if plugin5.triggered:
            triggered_plugins.append(plugin5)
            logger.info(f"[插件-急跌抢反弹] {stock_code} {date}: {plugin5.reason}, 直接发C")
            return 999, triggered_plugins  # 直接返回高分，确保发C
        
        return adjusted_score, triggered_plugins
    
    def _check_bearish_line(self, stock_code: str, date: datetime) -> CPointPluginResult:
        """
        插件1: 阴线检查
        任意阴线当日均不发C
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 优先使用缓存
            daily_data = self._daily_cache.get(date_str)
            if not daily_data:
                # 缓存未命中，查询数据库
                daily_data = self.daily_repo.find_by_date(stock_code, date_str)
            
            if not daily_data:
                return CPointPluginResult("阴线", False, 0, "")
            
            # 判断是否为阴线（收盘价 < 开盘价）
            if daily_data.close < daily_data.open:
                return CPointPluginResult(
                    "阴线",
                    True,
                    -999,  # 一票否决标记
                    f"阴线不发C (开盘:{daily_data.open:.2f}, 收盘:{daily_data.close:.2f})"
                )
            
            return CPointPluginResult("阴线", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-阴线检查失败: {e}")
            return CPointPluginResult("阴线", False, 0, "")
    
    def _check_high_ratio_low_win(self, stock_code: str, date: datetime) -> CPointPluginResult:
        """
        插件2: 赔率高胜率低
        如果因赔率较大带来的分值，且符合发C分值，但：
        1. 当日成交量未触及放量（ABCD）任意一种，且当日涨幅＜2%
        2. 前三个交易日成交量未能呈现ABCD任意一种，且当日也未能呈现成交量ABCD任意一种
        则扣减30分
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 优先使用缓存
            daily_data = self._daily_cache.get(date_str)
            if not daily_data:
                daily_data = self.daily_repo.find_by_date(stock_code, date_str)
            
            daily_chance = self._daily_chance_cache.get(date_str)
            if not daily_chance:
                daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            
            if not daily_data or not daily_chance:
                return CPointPluginResult("赔率高胜率低", False, 0, "")
            
            current_volume_type = daily_chance.volume_type or ""
            has_good_volume = any(t in current_volume_type for t in ['A', 'B', 'C', 'D'])
            
            # 计算涨幅
            change_pct = ((daily_data.close - daily_data.pre_close) / daily_data.pre_close * 100) if daily_data.pre_close else 0
            
            # 情况1: 当日成交量未触及放量（ABCD），且涨幅<2%
            if not has_good_volume and change_pct < 2:
                return CPointPluginResult(
                    "赔率高胜率低",
                    True,
                    -30,
                    f"当日无放量且涨幅<2% (成交量类型:{current_volume_type}, 涨幅:{change_pct:.2f}%)"
                )
            
            # 情况2: 前三天+当日都无ABCD
            if not has_good_volume:
                # 获取前三个交易日
                prev_dates = self._get_previous_trading_dates_from_cache(date_str)
                prev_has_good_volume = False
                
                for prev_date in prev_dates[:3]:
                    # 优先使用缓存
                    prev_chance = self._daily_chance_cache.get(prev_date)
                    if not prev_chance:
                        prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date)
                    
                    if prev_chance and prev_chance.volume_type:
                        if any(t in prev_chance.volume_type for t in ['A', 'B', 'C', 'D']):
                            prev_has_good_volume = True
                            break
                
                if not prev_has_good_volume:
                    return CPointPluginResult(
                        "赔率高胜率低",
                        True,
                        -30,
                        f"前三日及当日均无放量 (当日类型:{current_volume_type})"
                    )
            
            return CPointPluginResult("赔率高胜率低", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-赔率高胜率低检查失败: {e}")
            return CPointPluginResult("赔率高胜率低", False, 0, "")
    
    def _check_risk_kline(self, stock_code: str, date: datetime) -> CPointPluginResult:
        """
        插件3: 风险K线
        振幅＞6%/8%的冲高回落阳线、冲高回落阳十字星、带上影线的阳线不发C
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 优先使用缓存
            daily_data = self._daily_cache.get(date_str)
            if not daily_data:
                daily_data = self.daily_repo.find_by_date(stock_code, date_str)
            
            if not daily_data:
                return CPointPluginResult("风险K线", False, 0, "")
            
            # 判断是否为阳线
            is_bullish = daily_data.close >= daily_data.open
            if not is_bullish:
                return CPointPluginResult("风险K线", False, 0, "")
            
            # 计算振幅
            amplitude_pct = ((daily_data.high - daily_data.low) / daily_data.pre_close * 100) if daily_data.pre_close else 0
            
            # 判断振幅阈值（主板6%，非主板8%）
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            amplitude_threshold = 6 if is_main_board else 8
            
            if amplitude_pct <= amplitude_threshold:
                return CPointPluginResult("风险K线", False, 0, "")
            
            # 计算上影线比例
            body_high = max(daily_data.open, daily_data.close)
            upper_shadow = daily_data.high - body_high
            upper_shadow_ratio = (upper_shadow / (daily_data.high - daily_data.low)) if (daily_data.high - daily_data.low) > 0 else 0
            
            # 判断是否有明显上影线（上影线占比>30%）
            if upper_shadow_ratio > 0.3:
                return CPointPluginResult(
                    "风险K线",
                    True,
                    -999,  # 一票否决
                    f"冲高回落带上影线 (振幅:{amplitude_pct:.2f}%, 上影线比例:{upper_shadow_ratio*100:.1f}%)"
                )
            
            return CPointPluginResult("风险K线", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-风险K线检查失败: {e}")
            return CPointPluginResult("风险K线", False, 0, "")
    
    def _check_no_chase_high(self, stock_code: str, date: datetime) -> CPointPluginResult:
        """
        插件4: 不追涨
        如果当日符合发C的条件，但往前数三天涨幅过大，扣减50分
        
        情况：
        1）连续2个涨停
        2）前2日累计涨幅过大（主板15%，非主板25%）
        3）前3天累计涨幅过大（主板20%，非主板30%）
        4）已连续5天涨幅过大（主板30%，非主板40%）
        5）前两日连阳，且每日涨幅均大于5%以上
        
        股性为短线的除外
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # TODO: 判断股性（暂时先不考虑短线股）
            # is_short_term = self._check_stock_nature(stock_code)
            # if is_short_term:
            #     return CPointPluginResult("不追涨", False, 0, "")
            
            # 判断主板还是非主板
            is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
            
            # 获取前5个交易日数据（从缓存）
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 2:
                return CPointPluginResult("不追涨", False, 0, "")
            
            daily_data_list = []
            for prev_date in prev_dates[:5]:
                # 优先使用缓存
                data = self._daily_cache.get(prev_date)
                if not data:
                    data = self.daily_repo.find_by_date(stock_code, prev_date)
                if data:
                    daily_data_list.append(data)
            
            if len(daily_data_list) < 2:
                return CPointPluginResult("不追涨", False, 0, "")
            
            # 计算涨幅列表
            change_pcts = []
            for data in daily_data_list:
                if data.pre_close and data.pre_close > 0:
                    pct = (data.close - data.pre_close) / data.pre_close * 100
                    change_pcts.append(pct)
                else:
                    change_pcts.append(0)
            
            # 情况1: 连续2个涨停
            limit_threshold = 10 if is_main_board else 20
            if len(change_pcts) >= 2:
                if change_pcts[0] >= limit_threshold * 0.95 and change_pcts[1] >= limit_threshold * 0.95:
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"连续2个涨停 ({change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%)"
                    )
            
            # 情况2: 前2日累计涨幅过大
            if len(change_pcts) >= 2:
                cum_2days = sum(change_pcts[:2])
                threshold_2days = 15 if is_main_board else 25
                if cum_2days > threshold_2days:
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"前2日累计涨幅过大 (累计:{cum_2days:.2f}%, 阈值:{threshold_2days}%)"
                    )
            
            # 情况3: 前3天累计涨幅过大
            if len(change_pcts) >= 3:
                cum_3days = sum(change_pcts[:3])
                threshold_3days = 20 if is_main_board else 30
                if cum_3days > threshold_3days:
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"前3日累计涨幅过大 (累计:{cum_3days:.2f}%, 阈值:{threshold_3days}%)"
                    )
            
            # 情况4: 连续5天涨幅过大
            if len(change_pcts) >= 5:
                cum_5days = sum(change_pcts[:5])
                threshold_5days = 30 if is_main_board else 40
                if cum_5days > threshold_5days:
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"前5日累计涨幅过大 (累计:{cum_5days:.2f}%, 阈值:{threshold_5days}%)"
                    )
            
            # 情况5: 前两日连阳，且每日涨幅均大于5%
            if len(change_pcts) >= 2 and len(daily_data_list) >= 2:
                if (change_pcts[0] > 5 and change_pcts[1] > 5 and
                    daily_data_list[0].close >= daily_data_list[0].open and
                    daily_data_list[1].close >= daily_data_list[1].open):
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"前两日连阳且每日涨幅>5% ({change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%)"
                    )
            
            return CPointPluginResult("不追涨", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-不追涨检查失败: {e}")
            return CPointPluginResult("不追涨", False, 0, "")
    
    def _get_previous_trading_dates_from_cache(self, current_date_str: str) -> List[str]:
        """
        从缓存中获取前N个交易日的日期列表（性能优化版）
        
        Args:
            current_date_str: 当前日期字符串 'YYYY-MM-DD'
            
        Returns:
            前N个交易日的日期列表（按日期倒序）
        """
        try:
            # 从缓存中获取所有日期并排序
            all_dates = sorted(self._daily_cache.keys(), reverse=True)
            
            # 找到当前日期的位置，返回之前的日期
            result = []
            for date_str in all_dates:
                if date_str < current_date_str:
                    result.append(date_str)
            
            return result
            
        except Exception as e:
            logger.error(f"从缓存获取前N个交易日失败: {e}")
            return []
    
    def _get_previous_trading_dates(self, stock_code: str, current_date: datetime, days: int) -> List[str]:
        """获取前N个交易日的日期列表（降级方案，当缓存未初始化时使用）"""
        try:
            date_str = current_date.strftime('%Y-%m-%d') if isinstance(current_date, datetime) else current_date
            
            # 往前查询更多天数以确保有足够的交易日
            start_date = (current_date - timedelta(days=days*2)).strftime('%Y-%m-%d')
            
            daily_data_list = self.daily_repo.find_by_date_range(stock_code, start_date, date_str)
            
            # 按日期排序（降序）
            daily_data_list = sorted(daily_data_list, key=lambda x: x.date, reverse=True)
            
            # 排除当前日期，取前N个
            result = []
            for data in daily_data_list:
                data_date_str = data.date.strftime('%Y-%m-%d') if isinstance(data.date, datetime) else str(data.date)
                if data_date_str < date_str:
                    result.append(data_date_str)
                if len(result) >= days:
                    break
            
            return result
            
        except Exception as e:
            logger.error(f"获取前N个交易日失败: {e}")
            return []
    
    def _check_sharp_drop_rebound(self, stock_code: str, date: datetime) -> CPointPluginResult:
        """
        插件5: 急跌抢反弹
        
        主要条件（满足其一）：
        1）连续4日急跌且累计跌幅过大（主板20%，非主板25%）
        2）连续5日连续阴线且累计跌幅过大（主板20%，非主板30%）
        
        叠加条件（满足其一即发C）：
        A、今日成交量极度萎缩（相对第一日萎缩至20%）+ 振幅>5%的触底反弹十字星或阳线
        B、昨日成交量极度萎缩（相对第一日萎缩至20%）且昨日为十字星，今日为阳线
        
        满足条件直接发C（返回999分标记）
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
                return CPointPluginResult("急跌抢反弹", False, 0, "")
            
            # 获取前5个交易日数据
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 5:
                return CPointPluginResult("急跌抢反弹", False, 0, "")
            
            # 获取历史数据
            prev_data_list = []
            for prev_date in prev_dates[:5]:
                data = self._daily_cache.get(prev_date)
                if not data:
                    data = self.daily_repo.find_by_date(stock_code, prev_date)
                if data:
                    prev_data_list.append(data)
            
            if len(prev_data_list) < 4:
                return CPointPluginResult("急跌抢反弹", False, 0, "")
            
            # 计算涨跌幅列表（注意：prev_data_list[0]是最近的一天）
            change_pcts = []
            for data in prev_data_list:
                if data.pre_close and data.pre_close > 0:
                    pct = (data.close - data.pre_close) / data.pre_close * 100
                    change_pcts.append(pct)
                else:
                    change_pcts.append(0)
            
            # === 检查主要条件 ===
            main_condition_met = False
            main_reason = ""
            first_day_volume = 0  # 第一个下跌日的成交量
            
            # 条件1: 连续4日急跌且累计跌幅过大
            if len(change_pcts) >= 4:
                cum_4days = sum(change_pcts[:4])
                threshold_4days = -20 if is_main_board else -25
                if cum_4days < threshold_4days:
                    main_condition_met = True
                    main_reason = f"连续4日急跌(累计跌幅:{cum_4days:.2f}%)"
                    first_day_volume = prev_data_list[3].volume  # 第4天前（最早的一天）
            
            # 条件2: 连续5日连续阴线且累计跌幅过大
            if not main_condition_met and len(change_pcts) >= 5:
                all_bearish = all(prev_data_list[i].close < prev_data_list[i].open for i in range(5))
                cum_5days = sum(change_pcts[:5])
                threshold_5days = -20 if is_main_board else -30
                if all_bearish and cum_5days < threshold_5days:
                    main_condition_met = True
                    main_reason = f"连续5日阴线(累计跌幅:{cum_5days:.2f}%)"
                    first_day_volume = prev_data_list[4].volume  # 第5天前
            
            if not main_condition_met or first_day_volume == 0:
                return CPointPluginResult("急跌抢反弹", False, 0, "")
            
            # === 检查叠加条件 ===
            
            # 计算当日振幅
            current_amplitude = ((current_data.high - current_data.low) / current_data.pre_close * 100) if current_data.pre_close else 0
            
            # 判断当日是否为阳线
            is_current_bullish = current_data.close >= current_data.open
            
            # 判断当日是否为十字星（实体很小）
            current_body = abs(current_data.close - current_data.open)
            current_body_ratio = (current_body / current_data.close * 100) if current_data.close else 0
            is_current_doji = current_body_ratio < 1  # 实体占比<1%视为十字星
            
            # 条件A: 今日成交量极度萎缩 + 振幅>5%的触底反弹十字星或阳线
            current_volume_shrink = (current_data.volume / first_day_volume) if first_day_volume else 1
            if current_volume_shrink <= 0.2 and current_amplitude > 5:
                if is_current_doji or is_current_bullish:
                    pattern_type = "十字星" if is_current_doji else "阳线"
                    return CPointPluginResult(
                        "急跌抢反弹",
                        True,
                        999,  # 直接发C标记
                        f"{main_reason}, 今日量缩至{current_volume_shrink*100:.1f}%, 振幅{current_amplitude:.2f}%, {pattern_type}反弹"
                    )
            
            # 条件B: 昨日成交量极度萎缩且昨日为十字星，今日为阳线
            if len(prev_data_list) >= 1:
                yesterday_data = prev_data_list[0]
                yesterday_volume_shrink = (yesterday_data.volume / first_day_volume) if first_day_volume else 1
                
                # 判断昨日是否为十字星
                yesterday_body = abs(yesterday_data.close - yesterday_data.open)
                yesterday_body_ratio = (yesterday_body / yesterday_data.close * 100) if yesterday_data.close else 0
                is_yesterday_doji = yesterday_body_ratio < 1
                
                if yesterday_volume_shrink <= 0.2 and is_yesterday_doji and is_current_bullish:
                    return CPointPluginResult(
                        "急跌抢反弹",
                        True,
                        999,  # 直接发C标记
                        f"{main_reason}, 昨日量缩至{yesterday_volume_shrink*100:.1f}%且为十字星, 今日阳线反弹"
                    )
            
            return CPointPluginResult("急跌抢反弹", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-急跌抢反弹检查失败: {e}")
            return CPointPluginResult("急跌抢反弹", False, 0, "")

