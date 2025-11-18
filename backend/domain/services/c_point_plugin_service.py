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
        from domain.services.config_service import get_config_service
        self.daily_repo = DailyRepositoryImpl()
        self.daily_chance_repo = DailyChanceRepositoryImpl()
        self.config_service = get_config_service()
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
    
    def apply_plugins(self, stock_code: str, date: datetime, base_score: float, 
                     historical_r_points: Optional[List] = None, 
                     historical_c_points: Optional[List] = None) -> Tuple[float, List[CPointPluginResult], bool]:
        """
        应用所有插件，返回调整后的分数、触发的插件列表和是否强制发C的标志
        
        Args:
            stock_code: 股票代码
            date: 日期
            base_score: 基础分数（赔率分+胜率分）
            historical_r_points: 历史R点列表（可选，用于新插件）
            historical_c_points: 历史C点列表（可选，用于新插件）
            
        Returns:
            Tuple[final_score, triggered_plugins, force_c_point]: 
                (最终分数, 触发的插件列表, 是否强制发C)
        """
        triggered_plugins = []
        adjusted_score = base_score
        force_c_point = False  # 是否强制发C点
        
        # 插件1: 阴线检查（一票否决）
        plugin1 = self._check_bearish_line(stock_code, date)
        if plugin1.triggered:
            triggered_plugins.append(plugin1)
            logger.info(f"[插件-阴线] {stock_code} {date}: {plugin1.reason}")
            return 0, triggered_plugins, False  # 直接返回0分，不再检查其他插件
        
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
            return 0, triggered_plugins, False  # 一票否决
        
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
            logger.info(f"[插件-急跌抢反弹] {stock_code} {date}: {plugin5.reason}, 强制发C")
            return adjusted_score, triggered_plugins, True  # 强制发C，保持原分数
        
        # 插件6: R后回支撑位发C（直接发C）
        if historical_r_points is not None:
            plugin6 = self._check_r_back_to_support(stock_code, date, historical_r_points)
            if plugin6.triggered:
                triggered_plugins.append(plugin6)
                logger.info(f"[插件-R后回支撑位] {stock_code} {date}: {plugin6.reason}, 强制发C")
                return adjusted_score, triggered_plugins, True
        
        # 插件7: 阳包阴发C（直接发C）
        if historical_r_points is not None:
            plugin7 = self._check_yang_bao_yin(stock_code, date, historical_r_points)
            if plugin7.triggered:
                triggered_plugins.append(plugin7)
                logger.info(f"[插件-阳包阴] {stock_code} {date}: {plugin7.reason}, 强制发C")
                return adjusted_score, triggered_plugins, True
        
        # 插件8: 横盘修整后突破发C（直接发C）
        if historical_r_points is not None and historical_c_points is not None:
            plugin8 = self._check_consolidation_breakout(stock_code, date, historical_r_points, historical_c_points)
            if plugin8.triggered:
                triggered_plugins.append(plugin8)
                logger.info(f"[插件-横盘修整后突破] {stock_code} {date}: {plugin8.reason}, 强制发C")
                return adjusted_score, triggered_plugins, True
        
        return adjusted_score, triggered_plugins, False
    
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
                        0,  # 不调整分数，通过 force_c_point 标志直接发C
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
                        0,  # 不调整分数，通过 force_c_point 标志直接发C
                        f"{main_reason}, 昨日量缩至{yesterday_volume_shrink*100:.1f}%且为十字星, 今日阳线反弹"
                    )
            
            return CPointPluginResult("急跌抢反弹", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-急跌抢反弹检查失败: {e}")
            return CPointPluginResult("急跌抢反弹", False, 0, "")
    
    def _check_r_back_to_support(self, stock_code: str, date: datetime, historical_r_points: List) -> CPointPluginResult:
        """
        插件6: R后回支撑位发C
        
        条件：
        1. 在个股出R以后的3日内
        2. 重新回到支撑位上方或原本未跌破支撑
        3. 出现多头K线组合（1234任意一种）
        4. 当日成交量放大（ABCD任意一种）
        
        满足条件直接发C（返回999分标记）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 查找最近的R点（3日内）
            last_r_point = None
            for r_point in reversed(historical_r_points):
                r_date = r_point.trigger_date
                days_diff = (date - r_date).days
                if 0 < days_diff <= 3:
                    last_r_point = r_point
                    break
                elif days_diff > 3:
                    break  # 超过3天，不再查找
            
            if not last_r_point:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            # 获取支撑价格
            daily_chance = self._daily_chance_cache.get(date_str)
            if not daily_chance:
                daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not daily_chance or not daily_chance.support_price:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            support_price = daily_chance.support_price
            
            # 检查是否在支撑位上方（收盘价或最低价未跌破支撑位）
            is_above_support = current_data.close >= support_price or current_data.low >= support_price
            
            if not is_above_support:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            # 检查是否有多头K线组合（1234对应的名称）
            # 1=十字星+中阳线, 2=触底反弹阳线+阳线, 3=触底反弹阴线+中阳, 4=阳包阴
            bullish_pattern = daily_chance.bullish_pattern or ""
            if bullish_pattern:
                pattern_names_1234 = ["十字星+中阳线", "触底反弹阳线+阳线", "触底反弹阴线+中阳", "阳包阴"]
                pattern_list = [p.strip() for p in bullish_pattern.split(',')]
                has_bullish_pattern = any(p in pattern_names_1234 for p in pattern_list)
            else:
                has_bullish_pattern = False
            
            if not has_bullish_pattern:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            # 检查成交量放大（ABCD）
            volume_type = daily_chance.volume_type or ""
            has_volume_increase = any(t in volume_type for t in ['A', 'B', 'C', 'D'])
            
            if not has_volume_increase:
                return CPointPluginResult("R后回支撑位", False, 0, "")
            
            # 所有条件满足
            r_date_str = last_r_point.trigger_date.strftime('%Y-%m-%d')
            return CPointPluginResult(
                "R后回支撑位",
                True,
                0,  # 不调整分数，通过 force_c_point 标志直接发C
                f"R点后{(date - last_r_point.trigger_date).days}日, 回到支撑位上方({support_price:.2f}), 多头组合({bullish_pattern}), 放量({volume_type})"
            )
            
        except Exception as e:
            logger.error(f"插件-R后回支撑位检查失败: {e}")
            return CPointPluginResult("R后回支撑位", False, 0, "")
    
    def _check_yang_bao_yin(self, stock_code: str, date: datetime, historical_r_points: List) -> CPointPluginResult:
        """
        插件7: 阳包阴发C
        
        条件：
        1. 从当日往前数15根K线，若出现R
        2. R日放量（XYZH）
        3. 当日的收盘价 > R日的开盘价（阳包阴）
        4. 叠加条件（满足其一）：
           - 当日成交量 > R日成交量的0.85倍
           - 前一日为多头组合（任意）
        
        满足条件直接发C（返回999分标记）
        
        注意：此插件仅在牛市时生效
        """
        try:
            # 检查市场类型，只在牛市时生效
            market_type = self.config_service.get_market_type()
            if market_type != 'bull':
                return CPointPluginResult("阳包阴", False, 0, "")
            
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 获取前15个交易日
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 1:
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 查找15日内的R点
            r_point_in_range = None
            for r_point in reversed(historical_r_points):
                r_date = r_point.trigger_date
                r_date_str = r_date.strftime('%Y-%m-%d')
                
                # 检查R点是否在前15个交易日内
                if r_date_str in prev_dates[:15]:
                    # 检查R日是否放量（XYZH）
                    r_daily_chance = self._daily_chance_cache.get(r_date_str)
                    if not r_daily_chance:
                        r_daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, r_date_str)
                    
                    if r_daily_chance and r_daily_chance.volume_type:
                        has_r_volume = any(t in r_daily_chance.volume_type for t in ['X', 'Y', 'Z', 'H'])
                        if has_r_volume:
                            r_point_in_range = r_point
                            break
            
            if not r_point_in_range:
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 检查阳包阴：当日收盘价 > R日开盘价
            is_yang_bao_yin = current_data.close > r_point_in_range.open_price
            
            if not is_yang_bao_yin:
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 检查叠加条件1：当日成交量 > R日成交量的0.85倍
            volume_condition = current_data.volume > (r_point_in_range.volume * 0.85)
            
            # 检查叠加条件2：前一日为多头组合（任意）
            prev_bullish_condition = False
            if len(prev_dates) >= 1:
                prev_date = prev_dates[0]
                prev_chance = self._daily_chance_cache.get(prev_date)
                if not prev_chance:
                    prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date)
                
                # 前一日有多头组合（任意组合都算，不限定1234）
                if prev_chance and prev_chance.bullish_pattern:
                    prev_bullish_condition = len(prev_chance.bullish_pattern.strip()) > 0
            
            # 至少满足一个叠加条件
            if not (volume_condition or prev_bullish_condition):
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 所有条件满足
            r_date_str = r_point_in_range.trigger_date.strftime('%Y-%m-%d')
            condition_text = []
            if volume_condition:
                condition_text.append(f"当日量>{r_point_in_range.volume * 0.85:.0f}")
            if prev_bullish_condition:
                condition_text.append("前日多头组合")
            
            return CPointPluginResult(
                "阳包阴",
                True,
                0,  # 不调整分数，通过 force_c_point 标志直接发C
                f"R点({r_date_str}), 阳包阴(收{current_data.close:.2f}>R开{r_point_in_range.open_price:.2f}), {', '.join(condition_text)}"
            )
            
        except Exception as e:
            logger.error(f"插件-阳包阴检查失败: {e}")
            return CPointPluginResult("阳包阴", False, 0, "")
    
    def _check_consolidation_breakout(self, stock_code: str, date: datetime, 
                                     historical_r_points: List, historical_c_points: List) -> CPointPluginResult:
        """
        插件8: 横盘修整后突破发C
        
        条件：
        1. 往前数30个交易日，若发现R且R后无C
        2. R后的成交量均小于R日
        3. 今日成交量出现放量（AXYHZ任意一种）
        4. 股价突破R日收盘价
        
        满足条件直接发C（返回999分标记）
        
        注意：此插件仅在牛市时生效
        """
        try:
            # 检查市场类型，只在牛市时生效
            market_type = self.config_service.get_market_type()
            if market_type != 'bull':
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 获取当日成交量类型
            daily_chance = self._daily_chance_cache.get(date_str)
            if not daily_chance:
                daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not daily_chance:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 检查今日是否放量（AXYHZ）
            volume_type = daily_chance.volume_type or ""
            has_volume_increase = any(t in volume_type for t in ['A', 'X', 'Y', 'H', 'Z'])
            
            if not has_volume_increase:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 获取前30个交易日
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 1:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 查找30日内的R点，且R后无C
            target_r_point = None
            for r_point in reversed(historical_r_points):
                r_date = r_point.trigger_date
                r_date_str = r_date.strftime('%Y-%m-%d')
                
                # 检查R点是否在前30个交易日内
                if r_date_str in prev_dates[:30]:
                    # 检查R点之后是否有C点
                    has_c_after_r = False
                    for c_point in historical_c_points:
                        c_date = c_point.trigger_date
                        if r_date < c_date < date:
                            has_c_after_r = True
                            break
                    
                    if not has_c_after_r:
                        target_r_point = r_point
                        break
            
            if not target_r_point:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 检查R后的成交量均小于R日
            r_date = target_r_point.trigger_date
            r_date_str = r_date.strftime('%Y-%m-%d')
            r_volume = target_r_point.volume
            
            # 获取R点到当日之间的所有交易日
            dates_after_r = [d for d in prev_dates if d > r_date_str]
            
            all_volume_less_than_r = True
            for check_date in dates_after_r:
                check_data = self._daily_cache.get(check_date)
                if not check_data:
                    check_data = self.daily_repo.find_by_date(stock_code, check_date)
                
                if check_data and check_data.volume >= r_volume:
                    all_volume_less_than_r = False
                    break
            
            if not all_volume_less_than_r:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 检查股价突破R日收盘价
            is_breakout = current_data.close > target_r_point.close_price
            
            if not is_breakout:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 所有条件满足
            days_since_r = (date - target_r_point.trigger_date).days
            return CPointPluginResult(
                "横盘修整后突破",
                True,
                0,  # 不调整分数，通过 force_c_point 标志直接发C
                f"R点({r_date_str})后{days_since_r}日横盘, R后无C, 今日放量({volume_type})突破R收盘价({target_r_point.close_price:.2f})"
            )
            
        except Exception as e:
            logger.error(f"插件-横盘修整后突破检查失败: {e}")
            return CPointPluginResult("横盘修整后突破", False, 0, "")

