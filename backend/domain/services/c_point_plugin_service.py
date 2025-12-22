"""C点插件服务 - 优先级高于基础分数"""
from typing import Tuple, List, Optional, Any
from datetime import datetime, timedelta, date
from types import SimpleNamespace
from infrastructure.logging.logger import get_logger
from domain.services.kline_pattern_service import KLinePatternService

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
        self._sorted_dates = []  # 🚀 性能优化：缓存排序后的日期列表（避免重复排序）
    
    def init_cache(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        daily_list: Optional[List[Any]] = None,
        daily_chance_list: Optional[List[Any]] = None,
    ):
        """
        初始化数据缓存（批量查询）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始初始化插件缓存: {stock_code} {start_date} 至 {end_date}")
        
        # 批量查询 daily 数据（允许外部注入，避免重复IO）
        if daily_list is None:
            daily_list = self.daily_repo.find_by_date_range(stock_code, start_date, end_date)
        self._daily_cache = {}
        for daily in daily_list:
            date_str = daily.date.strftime('%Y-%m-%d') if isinstance(daily.date, datetime) else str(daily.date)
            self._daily_cache[date_str] = daily
        
        # 批量查询 daily_chance 数据（允许外部注入，避免重复IO）
        if daily_chance_list is None:
            daily_chance_list = self.daily_chance_repo.find_by_stock_code(stock_code, start_date, end_date)
        self._daily_chance_cache = {}
        for dc in daily_chance_list:
            date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
            self._daily_chance_cache[date_str] = dc
        
        # 🚀 性能优化：预排序日期列表（只排序一次，避免后续每次查询都排序）
        self._sorted_dates = sorted(self._daily_cache.keys(), reverse=True)
        
        logger.info(f"插件缓存初始化完成: daily={len(self._daily_cache)}条, daily_chance={len(self._daily_chance_cache)}条, 预排序日期={len(self._sorted_dates)}个")
    
    def clear_cache(self):
        """清空缓存"""
        self._daily_cache = {}
        self._daily_chance_cache = {}
        self._sorted_dates = []  # 🚀 性能优化：清空预排序列表

    @staticmethod
    def _parse_date(value):
        """将多种格式的日期值转换为datetime，失败则返回None"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            # 兼容 "YYYY-MM-DD" / "YYYY-MM-DD HH:MM:SS" / 带T的ISO格式
            candidate = value.replace("T", " ").split(".")[0]
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
        return None

    def _normalize_points(self, points: Optional[List]) -> Optional[List]:
        """
        将历史CR点列表统一为带属性的对象，兼容dict输入（triggerDate/trigger_date等）
        """
        if points is None:
            return None

        normalized = []
        for p in points:
            if hasattr(p, "trigger_date"):
                normalized.append(p)
                continue

            if isinstance(p, dict):
                trigger_raw = p.get("trigger_date") or p.get("triggerDate")
                trigger_dt = self._parse_date(trigger_raw)
                if not trigger_dt:
                    continue

                normalized.append(
                    SimpleNamespace(
                        trigger_date=trigger_dt,
                        volume=p.get("volume"),
                        high_price=p.get("high_price") or p.get("highPrice"),
                        close_price=p.get("close_price") or p.get("closePrice"),
                        plugins=p.get("plugins"),
                    )
                )
        return normalized
    
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

        # 兼容历史CR点字典输入，统一为带属性的对象
        normalized_r_points = self._normalize_points(historical_r_points)
        normalized_c_points = self._normalize_points(historical_c_points)
        
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
        
        # 插件5: 乖离率R后不发C（减分插件）
        if normalized_r_points is not None:
            deviation_plugin = self._check_deviation_r_penalty(stock_code, date, normalized_r_points)
            if deviation_plugin.triggered:
                triggered_plugins.append(deviation_plugin)
                adjusted_score += deviation_plugin.score_adjustment
                logger.info(f"[插件-乖离率R后不发C] {stock_code} {date}: {deviation_plugin.reason}, 扣分{abs(deviation_plugin.score_adjustment)}")
        
        # 插件6: 急跌抢反弹（直接发C）
        plugin6 = self._check_sharp_drop_rebound(stock_code, date)
        if plugin6.triggered:
            triggered_plugins.append(plugin6)
            logger.info(f"[插件-急跌抢反弹] {stock_code} {date}: {plugin6.reason}, 强制发C")
            return adjusted_score, triggered_plugins, True  # 强制发C，保持原分数
        
        # 插件7: R后回支撑位发C（直接发C）
        if normalized_r_points is not None:
            plugin7 = self._check_r_back_to_support(stock_code, date, normalized_r_points)
            if plugin7.triggered:
                triggered_plugins.append(plugin7)
                logger.info(f"[插件-R后回支撑位] {stock_code} {date}: {plugin7.reason}, 强制发C")
                return adjusted_score, triggered_plugins, True
        
        # 插件8: 阳包阴发C（直接发C）
        if normalized_r_points is not None:
            plugin8 = self._check_yang_bao_yin(stock_code, date, normalized_r_points, normalized_c_points)
            if plugin8.triggered:
                triggered_plugins.append(plugin8)
                logger.info(f"[插件-阳包阴] {stock_code} {date}: {plugin8.reason}, 强制发C")
                return adjusted_score, triggered_plugins, True
        
        # 插件9: 横盘修整后突破发C（直接发C）
        if normalized_r_points is not None and normalized_c_points is not None:
            plugin9 = self._check_consolidation_breakout(stock_code, date, normalized_r_points, normalized_c_points)
            if plugin9.triggered:
                triggered_plugins.append(plugin9)
                logger.info(f"[插件-横盘修整后突破] {stock_code} {date}: {plugin9.reason}, 强制发C")
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
        振幅＞6%/8%的空头分歧K线 减40分（一票否决）
        空头分歧K线包括：冲高回落阳线、冲高回落阳十字星、高振幅阳十字星
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
            # 注意：不要在本函数内部再次 import 同名 KLinePatternService，否则会导致 UnboundLocalError
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
            amplitude_threshold = 6 if is_main_board else 8
            
            if amplitude_pct <= amplitude_threshold:
                return CPointPluginResult("风险K线", False, 0, "")
            
            # 使用K线形态识别服务（已在文件顶部导入 KLinePatternService）
            pattern = KLinePatternService.identify_pattern(
                stock_code,
                daily_data.open,
                daily_data.close,
                daily_data.high,
                daily_data.low,
                daily_data.pre_close  # 传入前一日收盘价
            )
            
            # 检查是否为空头分歧K线
            risk_patterns = [
                "冲高回落阳线", 
                "冲高回落阳十字星", 
                "高振幅阳十字星"
            ]
            if pattern in risk_patterns:
                return CPointPluginResult(
                    "风险K线",
                    True,
                    -40,  # 扣40分，一票否决
                    f"{pattern} (振幅:{amplitude_pct:.2f}%)"
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
            
            # 判断股性，如果是短线则不触发此插件
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            
            allow_legacy_checks = True
            if current_chance and current_chance.stock_nature:
                stock_nature = current_chance.stock_nature
                # 新增条件需对所有股性生效，故仅对旧规则做豁免
                if stock_nature == "短线":
                    allow_legacy_checks = False
            
            # 判断主板还是非主板（统一规则）
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
            
            # 获取前6个交易日数据（多看一天，避免首日缺前收导致涨幅为0）
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 2:
                return CPointPluginResult("不追涨", False, 0, "")
            
            daily_data_list = []
            for prev_date in prev_dates[:6]:
                # 优先使用缓存
                data = self._daily_cache.get(prev_date)
                if not data:
                    data = self.daily_repo.find_by_date(stock_code, prev_date)
                if data:
                    daily_data_list.append(data)
            
            if len(daily_data_list) < 2:
                return CPointPluginResult("不追涨", False, 0, "")
            
            # 计算逐日涨幅（用于单日判断）；daily_data_list按日期从近到远
            change_pcts = []
            pct_records = []
            prev_close = None
            for data in daily_data_list:
                effective_prev = getattr(data, 'pre_close', None) or prev_close
                if effective_prev is not None and effective_prev > 0:
                    pct = (data.close - effective_prev) / effective_prev * 100
                    change_pcts.append(pct)
                    pct_records.append((pct, data))
                else:
                    change_pcts.append(0)
                prev_close = data.close

            def gain_by_span(n: int) -> Optional[float]:
                if len(daily_data_list) < n:
                    return None
                newest = daily_data_list[0].close
                oldest = daily_data_list[n-1].close
                if oldest is None or oldest <= 0 or newest is None:
                    return None
                return (newest - oldest) / oldest * 100
            
            if allow_legacy_checks:
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
                
                # 情况2: 前2日涨幅过大（起止收盘比）
                gain_2days = gain_by_span(2)
                if gain_2days is not None:
                    threshold_2days = 15 if is_main_board else 25
                    if gain_2days > threshold_2days:
                        return CPointPluginResult(
                            "不追涨",
                            True,
                            -50,
                            f"前2日涨幅过大 (涨幅:{gain_2days:.2f}%, 阈值:{threshold_2days}%)"
                        )
                
                # 情况3: 前3天涨幅过大（起止收盘比）
                gain_3days = gain_by_span(3)
                if gain_3days is not None:
                    threshold_3days = 20 if is_main_board else 30
                    if gain_3days > threshold_3days:
                        return CPointPluginResult(
                            "不追涨",
                            True,
                            -50,
                            f"前3日涨幅过大 (涨幅:{gain_3days:.2f}%, 阈值:{threshold_3days}%)"
                        )
                
                # 情况4: 连续5天涨幅过大（起止收盘比）
                gain_5days = gain_by_span(5)
                if gain_5days is not None:
                    threshold_5days = 30 if is_main_board else 40
                    if gain_5days > threshold_5days:
                        return CPointPluginResult(
                            "不追涨",
                            True,
                            -50,
                            f"前5日涨幅过大 (涨幅:{gain_5days:.2f}%, 阈值:{threshold_5days}%)"
                        )
                
                # 情况5: 前两日连阳，且每日涨幅均大于5%
                # 使用“最新的”两天涨幅（pct_records 按日期从新到旧），避免取到最老两天
                if len(pct_records) >= 2:
                    pct1, data1 = pct_records[0]  # 最近一天
                    pct2, data2 = pct_records[1]  # 次最近一天
                    if (pct1 > 5 and pct2 > 5 and
                        data1.close >= data1.open and
                        data2.close >= data2.open):
                        return CPointPluginResult(
                            "不追涨",
                            True,
                            -50,
                            f"前两日连阳且每日涨幅>5% ({pct1:.2f}%, {pct2:.2f}%)"
                        )

            # 新增情况6: 前5日均为阳线，且前5日涨幅达35%/50%（主板/非主板），对所有股性生效
            gain_5days_full = gain_by_span(5)
            if len(daily_data_list) >= 5 and gain_5days_full is not None:
                all_bullish = all(d.close > d.open for d in daily_data_list[:5])
                if all_bullish and gain_5days_full >= (35 if is_main_board else 50):
                    return CPointPluginResult(
                        "不追涨",
                        True,
                        -50,
                        f"前5日连阳且涨幅过大 (涨幅:{gain_5days_full:.2f}%)"
                    )
            
            return CPointPluginResult("不追涨", False, 0, "")
            
        except Exception as e:
            logger.error(f"插件-不追涨检查失败: {e}")
            return CPointPluginResult("不追涨", False, 0, "")
    
    def _check_deviation_r_penalty(self, stock_code: str, date: datetime, historical_r_points: List) -> CPointPluginResult:
        """
        插件5: 乖离率R后不发C（减分）
        
        条件：
        1. 前一个交易日出现有效R点
        2. 该R点由“乖离率偏离”插件触发
        
        结果：策略1当日C分数扣43分（全部股性适用）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            prev_dates = self._get_previous_trading_dates_from_cache(date_str)
            if not prev_dates and stock_code:
                prev_dates = self._get_previous_trading_dates(stock_code, date, 1)
            if not prev_dates:
                return CPointPluginResult("乖离率R后不发C", False, 0, "")
            
            prev_trading_date = prev_dates[0]
            last_r_point = None
            for r_point in reversed(historical_r_points):
                r_date = getattr(r_point, "trigger_date", None)
                if not r_date:
                    continue
                r_date_str = r_date.strftime('%Y-%m-%d') if isinstance(r_date, datetime) else str(r_date)
                if r_date_str == prev_trading_date:
                    last_r_point = r_point
                    break
                # 历史列表按时间升序传入，倒序查找到更早日期可提前结束
                if r_date_str < prev_trading_date:
                    break
            
            if not last_r_point:
                return CPointPluginResult("乖离率R后不发C", False, 0, "")
            
            plugins = getattr(last_r_point, "plugins", None) or []
            deviation_reason = ""
            for plugin in plugins:
                try:
                    name = plugin.get("pluginName") or plugin.get("plugin_name")
                    triggered = plugin.get("triggered", False)
                    if triggered and name == "乖离率偏离":
                        deviation_reason = plugin.get("reason") or ""
                        break
                except Exception:
                    continue
            
            if not deviation_reason:
                return CPointPluginResult("乖离率R后不发C", False, 0, "")
            
            return CPointPluginResult(
                "乖离率R后不发C",
                True,
                -43,
                f"昨日R由乖离率偏离触发: {deviation_reason}"
            )
        
        except Exception as e:
            logger.error(f"插件-乖离率R后不发C检查失败: {e}")
            return CPointPluginResult("乖离率R后不发C", False, 0, "")
    
    def _get_previous_trading_dates_from_cache(self, current_date_str: str) -> List[str]:
        """
        从缓存中获取前N个交易日的日期列表（性能优化版 - 使用预排序列表）
        
        🚀 性能优化：使用预排序的日期列表，避免每次调用都重新排序
        - 优化前：每次调用都要 sorted()，一个股票被调用数百次
        - 优化后：init_cache 时排序一次，后续直接使用
        - 提升：约10-15%性能提升
        
        Args:
            current_date_str: 当前日期字符串 'YYYY-MM-DD'
            
        Returns:
            前N个交易日的日期列表（按日期倒序）
        """
        try:
            # 🚀 直接使用预排序的日期列表，不需要再排序
            result = []
            for date_str in self._sorted_dates:
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
            
            # 判断主板还是非主板（统一规则）
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
            
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
            
            # 计算涨跌幅列表：使用当前收盘价相对前一日收盘价（不依赖数据库涨跌幅字段）
            # 注意：prev_data_list[0]是最近的一天
            change_pcts = []
            prev_close = None
            for data in prev_data_list:
                if prev_close is not None and prev_close > 0:
                    pct = (data.close - prev_close) / prev_close * 100
                    change_pcts.append(pct)
                else:
                    # 第一天或前一日收盘价无效，设为0
                    change_pcts.append(0)
                prev_close = data.close
            
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
            
            # 支撑位需要除以100（数据库存储的是整数形式，如1463代表14.63元）
            support_price = daily_chance.support_price / 100.0
            
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
    
    def _check_yang_bao_yin(self, stock_code: str, date: datetime, historical_r_points: List, historical_c_points: Optional[List] = None) -> CPointPluginResult:
        """
        插件7: 阳包阴发C
        
        条件：
        1. 从当日往前数15根K线，若出现R
        2. R点之后没有C点（前面最近的信号点是R，不是C）
        3. R日放量（XYZH）
        4. 当日的收盘价 > R日的最高价（阳包阴，完全突破）
        5. 叠加条件（满足其一）：
           - 当日成交量 > R日成交量的0.85倍
           - 前一日为多头组合（任意）
        
        满足条件直接发C（返回999分标记）
        
        注意：此插件仅在牛市时生效
        """
        try:
            # 检查市场类型，只在牛市时生效
            market_type = self.config_service.get_market_type(date)
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
            
            # 检查R点之后是否有C点（前面最近的信号点必须是R，不能是C）
            # 从R点日期到今天之间，检查是否有C点
            r_date = r_point_in_range.trigger_date
            has_c_after_r = False
            
            # 从历史C点中查找R点之后、今天之前的C点
            if historical_c_points:
                for c_point in historical_c_points:
                    c_date = c_point.trigger_date if hasattr(c_point, 'trigger_date') else c_point.get('trigger_date')
                    if c_date and r_date < c_date < date:
                        has_c_after_r = True
                        break
            
            # 如果R点之后已经有C点，则不再发C
            if has_c_after_r:
                return CPointPluginResult("阳包阴", False, 0, "")
            
            # 检查阳包阴：当日收盘价 > R日最高价（完全突破）
            is_yang_bao_yin = current_data.close > r_point_in_range.high_price
            
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
                condition_text.append("当日成交量>R日成交量的0.85倍")
            if prev_bullish_condition:
                condition_text.append("前日多头组合")
            
            return CPointPluginResult(
                "阳包阴",
                True,
                0,  # 不调整分数，通过 force_c_point 标志直接发C
                f"R点({r_date_str}), 阳包阴(收{current_data.close:.2f}>R高{r_point_in_range.high_price:.2f}), R后无C, {', '.join(condition_text)}"
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
        4. 当日股价 > R日最高价
        5. 今日距离R日 >= 5个交易日
        
        满足条件直接发C（返回999分标记）
        
        注意：此插件仅在牛市时生效
        """
        try:
            # 检查市场类型，只在牛市时生效
            market_type = self.config_service.get_market_type(date)
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
            
            # 需至少5个交易日间隔
            if len(dates_after_r) < 5:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
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
            
            # 检查股价突破R日最高价
            is_breakout = current_data.close > target_r_point.high_price
            
            if not is_breakout:
                return CPointPluginResult("横盘修整后突破", False, 0, "")
            
            # 所有条件满足
            days_since_r = (date - target_r_point.trigger_date).days
            return CPointPluginResult(
                "横盘修整后突破",
                True,
                0,  # 不调整分数，通过 force_c_point 标志直接发C
                f"R点({r_date_str})后{days_since_r}日横盘, R后无C, 今日放量({volume_type})突破R最高价({target_r_point.high_price:.2f})"
            )
            
        except Exception as e:
            logger.error(f"插件-横盘修整后突破检查失败: {e}")
            return CPointPluginResult("横盘修整后突破", False, 0, "")

