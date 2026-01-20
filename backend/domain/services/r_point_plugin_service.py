"""R点插件服务 - 风险信号检测"""
from typing import Tuple, List, Optional
from datetime import datetime, timedelta, date
from infrastructure.logging.logger import get_logger
from domain.services.kline_pattern_service import KLinePatternService
from domain.services.macd_service import MACDService
import pymysql
import pymysql.cursors

logger = get_logger(__name__)

# 只读库配置（用于查询换手率数据）
READONLY_DB_CONFIG = {
    'host': 'sh-cdbrg-8f14w39q.sql.tencentcdb.com',
    'port': 25924,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 10,
}




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
        from domain.services.config_service import get_config_service
        self.daily_repo = DailyRepositoryImpl()
        self.daily_chance_repo = DailyChanceRepositoryImpl()
        self.config_service = get_config_service()  # 使用单例，确保配置更新后生效
        # 数据缓存
        self._daily_cache = {}  # {date_str: DailyData}
        self._daily_chance_cache = {}  # {date_str: DailyChance}
        self._sorted_dates = []  # 🚀 性能优化：预排序日期列表，避免每次都 sorted()
        self._cr_history_cache = {}  # {(stock_code, cutoff_date): {'c': [...], 'r': [...]}}
        # kline_data 日期->索引缓存：用于按“C点日期”取 MA20/MACD 序列值
        self._kline_date_index_cache_key = None
        self._kline_date_index_cache = None
        # 🚀 性能优化：换手率缓存（优先来自已预加载的 daily_chance.huanshou）
        # {date_str: huanshou_percent_float}
        self._turnover_rate_cache = {}
        # 懒加载只读库批量预取：仅在确实需要换手率且缓存缺失时触发一次
        self._turnover_prefetch_attempted = False
        self._turnover_prefetch_stock_code = None
        self._turnover_prefetch_start_date = None
        self._turnover_prefetch_end_date = None
    
    def init_cache(self, stock_code: str, start_date: str, end_date: str,
                   daily_list: Optional[list] = None,
                   daily_chance_list: Optional[list] = None):
        """
        初始化数据缓存（批量查询）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始初始化R点插件缓存: {stock_code} {start_date} 至 {end_date}")
        
        # 批量查询 daily 数据（允许外部注入，避免重复IO）
        if daily_list is None:
            daily_list = self.daily_repo.find_by_date_range(stock_code, start_date, end_date)
        self._daily_cache = {}
        for daily in daily_list:
            date_str = daily.date.strftime('%Y-%m-%d') if isinstance(daily.date, datetime) else str(daily.date)
            self._daily_cache[date_str] = daily

        # 🚀 性能优化：预排序日期列表（只排序一次）
        self._sorted_dates = sorted(self._daily_cache.keys(), reverse=True)
        
        # 批量查询 daily_chance 数据（允许外部注入，避免重复IO）
        if daily_chance_list is None:
            daily_chance_list = self.daily_chance_repo.find_by_stock_code(stock_code, start_date, end_date)
        self._daily_chance_cache = {}
        self._turnover_rate_cache = {}
        self._turnover_prefetch_attempted = False
        self._turnover_prefetch_stock_code = stock_code
        self._turnover_prefetch_start_date = start_date
        self._turnover_prefetch_end_date = end_date
        for dc in daily_chance_list:
            date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
            self._daily_chance_cache[date_str] = dc
            try:
                hs = getattr(dc, "huanshou", None)
                if hs is not None:
                    self._turnover_rate_cache[date_str] = float(hs)
            except Exception:
                # huanshou 不可解析时忽略
                pass
        
        logger.info(f"R点插件缓存初始化完成: daily={len(self._daily_cache)}条, daily_chance={len(self._daily_chance_cache)}条")
    
    def clear_cache(self):
        """清空缓存"""
        self._daily_cache = {}
        self._daily_chance_cache = {}
        self._sorted_dates = []
        self._kline_date_index_cache_key = None
        self._kline_date_index_cache = None
        self._turnover_rate_cache = {}
        self._turnover_prefetch_attempted = False
        self._turnover_prefetch_stock_code = None
        self._turnover_prefetch_start_date = None
        self._turnover_prefetch_end_date = None
    
    def check_r_point(self, stock_code: str, date: datetime, c_point_date: Optional[datetime] = None,
                     ma_data: Optional[dict] = None, macd_data: Optional[dict] = None, 
                     current_index: Optional[int] = None, kline_data: Optional[list] = None,
                     last_valid_point_type: Optional[str] = None,
                     last_c_point_type: Optional[str] = None,
                     historical_c_points: Optional[list] = None,
                     historical_r_points: Optional[list] = None) -> Tuple[bool, List[RPointPluginResult]]:
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
        
        # 测试插件：熊市直接发R（已禁用）
        # bear_test = self._check_bear_market_test(stock_code, date, c_point_date, last_valid_point_type, last_c_point_type)
        # if bear_test.triggered:
        #     triggered_plugins.append(bear_test)
        #     logger.info(f"[R点插件-熊市测试R] {stock_code} {date}: {bear_test.reason}")
        #     return True, triggered_plugins
        
        # 插件1: 乖离率偏离
        plugin1 = self._check_deviation(stock_code, date, ma_data, current_index)
        if plugin1.triggered:
            triggered_plugins.append(plugin1)
            logger.info(f"[R点插件-乖离率偏离] {stock_code} {date}: {plugin1.reason}")
            return True, triggered_plugins

        # 插件3: 强转弱且未反转
        plugin3_strong_to_weak = self._check_strong_to_weak_not_reversed(stock_code, date)
        if plugin3_strong_to_weak.triggered:
            triggered_plugins.append(plugin3_strong_to_weak)
            logger.info(f"[R点插件-强转弱未反转] {stock_code} {date}: {plugin3_strong_to_weak.reason}")
            return True, triggered_plugins
        
        # 插件4: 基本面突发利空
        plugin4 = self._check_fundamental_negative(stock_code, date)
        if plugin4.triggered:
            triggered_plugins.append(plugin4)
            logger.info(f"[R点插件-基本面突发利空] {stock_code} {date}: {plugin4.reason}")
            return True, triggered_plugins

        # 插件5: 上冲乏力（熊市特定逻辑）
        if c_point_date:
            plugin5 = self._check_weak_breakout(stock_code, date, c_point_date, last_valid_point_type)
            if plugin5.triggered:
                triggered_plugins.append(plugin5)
                logger.info(f"[R点插件-上冲乏力] {stock_code} {date}: {plugin5.reason}")
                return True, triggered_plugins

        # 插件6: 跌破支撑位
        plugin6 = self._check_break_support(stock_code, date, c_point_date)
        if plugin6.triggered:
            triggered_plugins.append(plugin6)
            logger.info(f"[R点插件-跌破支撑位] {stock_code} {date}: {plugin6.reason}")
            return True, triggered_plugins

        # 插件14: 横盘震荡+风险信号
        # 依赖：历史C/R点序列（C不落库，只能由上层 analyze 循环传入），以及 MA/MACD 序列用于横盘与风险判定
        if kline_data is not None and current_index is not None and ma_data is not None and (historical_c_points or historical_r_points):
            plugin14 = self._check_sideways_oscillation_risk(
                stock_code=stock_code,
                date=date,
                ma_data=ma_data,
                macd_data=macd_data,
                current_index=current_index,
                kline_data=kline_data,
                historical_c_points=historical_c_points or [],
                historical_r_points=historical_r_points or [],
            )
            if plugin14.triggered:
                triggered_plugins.append(plugin14)
                logger.info(f"[R点插件-横盘震荡+风险信号] {stock_code} {date}: {plugin14.reason}")
                return True, triggered_plugins

        # 插件13: 阶段涨幅过大（30交易日涨幅>=30% + 任意量型 + 跌破MA20(昨>今<) + DIF<DEA）
        if ma_data and macd_data and current_index is not None:
            plugin13 = self._check_stage_rally_too_high(stock_code, date, ma_data, macd_data, current_index)
            if plugin13.triggered:
                triggered_plugins.append(plugin13)
                logger.info(f"[R点插件-阶段涨幅过大] {stock_code} {date}: {plugin13.reason}")
                return True, triggered_plugins
        
        # 插件7: 高位发R
        if ma_data and macd_data and current_index is not None:
            plugin7 = self._check_high_position_r(stock_code, date, ma_data, macd_data, current_index, c_point_date)
            if plugin7.triggered:
                triggered_plugins.append(plugin7)
                logger.info(f"[R点插件-高位发R] {stock_code} {date}: {plugin7.reason}")
                return True, triggered_plugins

        # 插件8: 箱体回踩被跌破
        if macd_data and current_index is not None and kline_data is not None:
            plugin8 = self._check_box_breakdown(stock_code, date, macd_data, current_index, kline_data, c_point_date)
            if plugin8.triggered:
                triggered_plugins.append(plugin8)
                logger.info(f"[R点插件-箱体回踩被跌破] {stock_code} {date}: {plugin8.reason}")
                return True, triggered_plugins

        # 插件9: 趋势向下+未放量跌破支撑+MACD死叉
        # 新逻辑依赖“上个C是否为低位C”，以及上个低位C当日支撑位，因此需要kline_data + c_point_date
        if ma_data and macd_data and current_index is not None and kline_data is not None and c_point_date:
            plugin9 = self._check_downtrend_break_support(
                stock_code, date, ma_data, macd_data, current_index, kline_data, c_point_date
            )
            if plugin9.triggered:
                triggered_plugins.append(plugin9)
                logger.info(f"[R点插件-趋势向下+未放量跌破支撑+MACD死叉] {stock_code} {date}: {plugin9.reason}")
                return True, triggered_plugins

        # 插件11: MACD中长线死叉+跌破支撑
        if macd_data and current_index is not None:
            plugin11 = self._check_macd_long_dead_cross_break_support(stock_code, date, macd_data, current_index, c_point_date)
            if plugin11.triggered:
                triggered_plugins.append(plugin11)
                logger.info(f"[R点插件-MACD中长线死叉+跌破支撑] {stock_code} {date}: {plugin11.reason}")
                return True, triggered_plugins

        # 插件15: 趋势走弱 (中长线/波段 + 放量 + MACD死叉 + 跌破MA20 + 风险信号)
        if ma_data and macd_data and current_index is not None and kline_data is not None:
            plugin15 = self._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_data)
            if plugin15.triggered:
                triggered_plugins.append(plugin15)
                logger.info(f"[R点插件-趋势走弱] {stock_code} {date}: {plugin15.reason}")
                return True, triggered_plugins


        # 插件12: 中长线顶背离（仅中长线股性）
        if macd_data and current_index is not None and kline_data is not None:
            plugin12 = self._check_macd_long_top_divergence(stock_code, date, macd_data, current_index, kline_data)
            if plugin12.triggered:
                triggered_plugins.append(plugin12)
                logger.info(f"[R点插件-中长线顶背离] {stock_code} {date}: {plugin12.reason}")
                return True, triggered_plugins

        # 插件10: 高位滞涨
        if ma_data and macd_data and current_index is not None:
            plugin10 = self._check_high_stagnation_bearish(stock_code, date, ma_data, macd_data, current_index, c_point_date)
            if plugin10.triggered:
                triggered_plugins.append(plugin10)
                logger.info(f"[R点插件-高位滞涨] {stock_code} {date}: {plugin10.reason}")
                return True, triggered_plugins

        # 插件2: 临近压力位滞涨（放最后，避免缺C点影响其他插件）
        plugin2 = self._check_pressure_stagnation(
            stock_code,
            date,
            c_point_date,
            last_valid_point_type,
            macd_data=macd_data,
            current_index=current_index,
            historical_c_points=historical_c_points,
            historical_r_points=historical_r_points,
        )
        if plugin2.triggered:
            triggered_plugins.append(plugin2)
            logger.info(f"[R点插件-临近压力位滞涨] {stock_code} {date}: {plugin2.reason}")
            return True, triggered_plugins

        return False, triggered_plugins


    # =========================
    # 插件15：趋势走弱
    # =========================
    def _check_trend_weakening(
        self,
        stock_code: str,
        date: datetime,
        ma_data: dict,
        macd_data: dict,
        current_index: int,
        kline_data: list
    ) -> RPointPluginResult:
        """
        插件15: 趋势走弱 (仅针对中长线和波段股性)
        
        触发条件（必须全部满足）：
        1. 股性为“中长线”或“波段”。
        2. 放量：volume_type 包含 ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'Z', 'Y', 'S'] 中任意一个。
        3. MACD死叉：DIF < DEA。
        4. 跌破均线：收盘价 <= MA20。
        5. 风险信号（满足其一）：
           - 出现空头组合 (bearish_pattern 非空)。
           - 分歧K线：["冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", "冲高回落阴十字星", "高开低走"] 中任意一个。
           - 大阴线：跌幅 (PrevClose - Close)/PrevClose > 3% 且 实体跌幅 (Open - Close)/PrevClose > 3%。
        """
        plugin_name = "趋势走弱"
        
        # 0. 准备数据
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
        daily_chance = self._daily_chance_cache.get(date_str)
        
        # 1. 股性检查：仅中长线和波段
        stock_nature = "波段" # 默认为波段
        if daily_chance and getattr(daily_chance, "stock_nature", None):
            stock_nature = daily_chance.stock_nature
            
        if stock_nature not in ["中长线", "波段"]:
             return RPointPluginResult(plugin_name, False, "")

        # 2. 放量检查
        volume_type = getattr(daily_chance, "volume_type", None)
        if not volume_type:
             return RPointPluginResult(plugin_name, False, "")
             
        valid_volume_types = {'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'Z', 'Y', 'S'}
        # volume_type 可能包含多个类型，如 "A,H"
        current_types = set(t.strip() for t in volume_type.split(','))
        if not current_types.intersection(valid_volume_types):
             return RPointPluginResult(plugin_name, False, "")

        # 3. MACD死叉检查 (DIF < DEA)
        if not macd_data or not macd_data.get('dif') or not macd_data.get('dea'):
             return RPointPluginResult(plugin_name, False, "")
             
        dif_list = macd_data['dif']
        dea_list = macd_data['dea']
        
        if current_index >= len(dif_list) or current_index >= len(dea_list):
             return RPointPluginResult(plugin_name, False, "")
             
        dif = dif_list[current_index]
        dea = dea_list[current_index]
        
        if dif is None or dea is None or dif >= dea:
             return RPointPluginResult(plugin_name, False, "")

        # 4. 跌破均线检查 (Close <= MA20)
        current_kline = kline_data[current_index]
        close_price = current_kline.close
        
        ma20_list = ma_data.get('ma20', [])
        if current_index >= len(ma20_list):
             return RPointPluginResult(plugin_name, False, "")
             
        ma20 = ma20_list[current_index]
        if ma20 is None or close_price > ma20:
             return RPointPluginResult(plugin_name, False, "")

        # 5. 风险信号检查 (满足其一)
        risk_signal_found = False
        risk_reason = ""

        # 5.1 空头组合
        bearish_pattern = getattr(daily_chance, "bearish_pattern", None)
        if bearish_pattern:
            risk_signal_found = True
            risk_reason = f"空头组合: {bearish_pattern}"

        # 5.2 分歧K线
        if not risk_signal_found:
            divergence_patterns = {
                "冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", 
                "冲高回落阴十字星", "高开低走"
            }
            # K线形态通常也在 bearish_pattern 或 bullish_pattern 中体现，或者需要单独计算
            # 这里假设如果 bearish_pattern 中包含了这些描述，或者我们需要额外检查形态
            # 由于 daily_chance.bearish_pattern 已经包含了识别出的空头形态，
            # 如果这里的“分歧K线”是 daily_chance 里的标准形态，那上一条已经覆盖。
            # 这里为了保险，检查 bearish_pattern 是否包含这些特定字符串
            if bearish_pattern and any(p in bearish_pattern for p in divergence_patterns):
                 risk_signal_found = True
                 risk_reason = f"分歧K线: {bearish_pattern}"

        # 5.3 大阴线 (跌幅 > 3% 且 实体跌幅 > 3%)
        if not risk_signal_found:
            prev_close = 0
            if current_index > 0:
                prev_close = kline_data[current_index - 1].close
            elif 'prev_close' in kline_data[current_index].__dict__: # 尝试从对象属性获取
                 prev_close = kline_data[current_index].prev_close
            
            if prev_close > 0:
                drop_pct = (prev_close - close_price) / prev_close
                open_price = current_kline.open
                # 实体跌幅: (Open - Close) / PrevClose (严格来说应该是实体长度相对于昨收)
                # 用户描述: "跌幅（相对于昨收）大于3%的阴线（且B＞3%）"
                # B通常指实体 (Body)。在这里理解为实体长度 > 3% 昨收。
                # 且必须是阴线 (Open > Close)
                if open_price > close_price:
                    body_pct = (open_price - close_price) / prev_close
                    if drop_pct > 0.03 and body_pct > 0.03:
                        risk_signal_found = True
                        risk_reason = f"大阴线(跌幅{drop_pct*100:.1f}%, 实体{body_pct*100:.1f}%)"

        if risk_signal_found:
            return RPointPluginResult(
                plugin_name, 
                True, 
                f"放量+MACD死叉+跌破MA20+风险信号({risk_reason})"
            )
            
        return RPointPluginResult(plugin_name, False, "")

    # =========================
    # 插件14：横盘震荡+风险信号
    # =========================
    def _check_sideways_oscillation_risk(
        self,
        stock_code: str,
        date: datetime,
        ma_data: dict,
        macd_data: Optional[dict],
        current_index: int,
        kline_data: list,
        historical_c_points: list,
        historical_r_points: list,
    ) -> RPointPluginResult:
        """
        横盘震荡+风险信号（用户定义版）

        横盘阶段判定（以“最近一次R之后的连续C序列”为横盘锚定）：
        - 从“今日之前”的最后一个有效信号开始回溯，若上个信号是C，则继续向前找上上个C，直到再上个是R；
          取这段 C 序列中：
            - 离上个R最近的第一个C（最早的C / 离今天最远的C） 记为 firstC
            - 今日最近的上个C（最新的C）记为 lastC
        - 认为处于横盘阶段需同时满足：
            1) abs(lastC_support - firstC_support) / firstC_support < 6%
            2) abs(lastC_open - firstC_open) / firstC_open < 2%
            3) 对该段内每个C点日：abs(C_open - C_MA20) / C_open < 6%
        - 横盘阶段“直到下个R为止”（在CR循环里，本插件触发即产生下个R，结束横盘）

        横盘阶段内的风险触发（满足任一即出R）：
        1) 跌破或已跌破 MA20 + MACD已死叉(DEA>DIF)
        2) 跌破或已跌破 最近C日支撑位 + MACD已死叉(DEA>DIF)
        3) 当日有任意成交量类型 + 跌破或已跌破 最近C日支撑位
        4) 当日有任意成交量类型 + 跌破或已跌破 MA20
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date)

            # 需要 MA20 序列
            ma20_list = ma_data.get("ma20") if isinstance(ma_data, dict) else None
            if not ma20_list or current_index >= len(ma20_list):
                return RPointPluginResult("横盘震荡+风险信号", False, "")
            ma20_today = ma20_list[current_index]
            if ma20_today is None or ma20_today <= 0:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            # 当前日数据
            current_data = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("横盘震荡+风险信号", False, "")
            current_close = getattr(current_data, "close", 0) or 0
            current_low = getattr(current_data, "low", 0) or 0

            # 当前日 daily_chance（成交量类型）
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            volume_type_str = getattr(current_chance, "volume_type", None) if current_chance else None
            has_any_volume_type = bool(str(volume_type_str).strip()) if volume_type_str is not None else False

            # 组装“今日之前”的有效点序列（来自上层传入的历史点列表；C不落库，必须依赖该序列）
            points = []
            for p in (historical_c_points or []) + (historical_r_points or []):
                info = self._extract_cr_point_info(p)
                if not info:
                    continue
                # 只考虑今日之前
                if info["dt"] and info["dt"] < date:
                    points.append(info)

            if not points:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            points.sort(key=lambda x: x["dt"])
            last_sig = points[-1]
            if last_sig["type"] != "C":
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            # 回溯：从 last_sig 往前数连续的C，直到遇到R
            idx = len(points) - 1
            j = idx - 1
            while j >= 0 and points[j]["type"] == "C":
                j -= 1
            if j < 0 or points[j]["type"] != "R":
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            c_segment = points[j + 1 : idx + 1]  # 连续C序列（R之后）
            if len(c_segment) < 2:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            first_c = c_segment[0]  # 离上个R最近的第一个C（最早的C）
            last_c = c_segment[-1]  # 今日最近的上个C（最新的C）

            # 取C点支撑位（来自 daily_chance.support_price）
            first_support = self._get_support_price_actual(stock_code, first_c["date_str"])
            last_support = self._get_support_price_actual(stock_code, last_c["date_str"])
            if not first_support or not last_support or first_support <= 0:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            # 取C点开盘价（优先来自点本身；兜底用 daily）
            first_open = first_c.get("open_price") or self._get_daily_open(stock_code, first_c["date_str"])
            last_open = last_c.get("open_price") or self._get_daily_open(stock_code, last_c["date_str"])
            if not first_open or not last_open or first_open <= 0:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            support_delta_pct = abs(last_support - first_support) / first_support * 100
            open_delta_pct = abs(last_open - first_open) / first_open * 100
            if support_delta_pct >= 6.0 or open_delta_pct >= 2.0:
                return RPointPluginResult("横盘震荡+风险信号", False, "")

            # 每个C点日：开盘价与MA20接近
            for c_info in c_segment:
                c_open = c_info.get("open_price") or self._get_daily_open(stock_code, c_info["date_str"])
                if not c_open or c_open <= 0:
                    return RPointPluginResult("横盘震荡+风险信号", False, "")
                c_ma20 = self._get_ma20_by_date_str(ma20_list, kline_data, c_info["date_str"])
                if c_ma20 is None or c_ma20 <= 0:
                    return RPointPluginResult("横盘震荡+风险信号", False, "")
                ma20_delta_pct = abs(c_open - c_ma20) / c_open * 100
                if ma20_delta_pct >= 6.0:
                    return RPointPluginResult("横盘震荡+风险信号", False, "")

            # 横盘阶段成立，开始判断风险触发
            # 最近1个C的支撑位
            last_c_support = last_support

            # 取前一交易日（用于“已跌破”）
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            prev_date_str = prev_dates[0] if prev_dates else None
            prev_data = None
            prev_ma20 = None
            if prev_date_str:
                prev_data = self._daily_cache.get(prev_date_str) or self.daily_repo.find_by_date(stock_code, prev_date_str)
                if current_index - 1 >= 0 and current_index - 1 < len(ma20_list):
                    prev_ma20 = ma20_list[current_index - 1]

            def _below_or_was_below_price(threshold: float) -> bool:
                # 简化逻辑：只检查当日收盘价是否低于阈值
                # 如果当日收盘价低于C日支撑位，就算跌破或已跌破
                return current_close and threshold > 0 and current_close < threshold

            def _below_or_was_below_ma20() -> bool:
                # 简化逻辑：只检查当日收盘价是否在当日MA20以下
                # 如果当日收盘价低于MA20，就算跌破或已跌破
                return current_close and ma20_today and current_close < ma20_today

            # MACD死叉状态：DEA > DIF
            is_dead_cross = False
            dif_v = None
            dea_v = None
            if macd_data and isinstance(macd_data, dict):
                dif_list = macd_data.get("dif") or []
                dea_list = macd_data.get("dea") or []
                if current_index < len(dif_list) and current_index < len(dea_list):
                    dif_v = dif_list[current_index]
                    dea_v = dea_list[current_index]
                    if dif_v is not None and dea_v is not None:
                        is_dead_cross = dea_v > dif_v

            # 获取前一日支撑位（用于动态支撑比较）
            prev_support_val = 0.0
            if prev_date_str:
                prev_chance = self._daily_chance_cache.get(prev_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
                if prev_chance and prev_chance.support_price:
                    prev_support_val = float(prev_chance.support_price) / 100.0

            # 动态支撑位：MAX(最近C日支撑, 前一日支撑)
            final_c_support = max(last_c_support, prev_support_val)

            break_ma20 = _below_or_was_below_ma20()
            break_c_support = _below_or_was_below_price(final_c_support)

            # 规则1/2 需要死叉；3/4 需要任意量型
            if break_ma20 and is_dead_cross:
                return RPointPluginResult(
                    "横盘震荡+风险信号",
                    True,
                    f"横盘成立(firstC={first_c['date_str']},lastC={last_c['date_str']},支撑差{support_delta_pct:.2f}%,开盘差{open_delta_pct:.2f}%) "
                    f"+ 跌破/已跌破MA20({ma20_today:.2f}) + MACD死叉(DEA>{dea_v if dea_v is not None else 'None'},DIF={dif_v if dif_v is not None else 'None'})"
                )

            if break_c_support and is_dead_cross:
                return RPointPluginResult(
                    "横盘震荡+风险信号",
                    True,
                    f"横盘成立(firstC={first_c['date_str']},lastC={last_c['date_str']},支撑差{support_delta_pct:.2f}%,开盘差{open_delta_pct:.2f}%) "
                    f"+ 跌破/已跌破C后动态支撑({final_c_support:.2f}) + MACD死叉(DEA>{dea_v if dea_v is not None else 'None'},DIF={dif_v if dif_v is not None else 'None'})"
                )

            if has_any_volume_type and break_c_support:
                return RPointPluginResult(
                    "横盘震荡+风险信号",
                    True,
                    f"横盘成立(firstC={first_c['date_str']},lastC={last_c['date_str']},支撑差{support_delta_pct:.2f}%,开盘差{open_delta_pct:.2f}%) "
                    f"+ 任意量型({volume_type_str}) + 跌破/已跌破C后动态支撑({final_c_support:.2f})"
                )

            if has_any_volume_type and break_ma20:
                return RPointPluginResult(
                    "横盘震荡+风险信号",
                    True,
                    f"横盘成立(firstC={first_c['date_str']},lastC={last_c['date_str']},支撑差{support_delta_pct:.2f}%,开盘差{open_delta_pct:.2f}%) "
                    f"+ 任意量型({volume_type_str}) + 跌破/已跌破MA20({ma20_today:.2f})"
                )

            return RPointPluginResult("横盘震荡+风险信号", False, "")
        except Exception as e:
            logger.error(f"R点插件-横盘震荡+风险信号检查失败: {e}")
            return RPointPluginResult("横盘震荡+风险信号", False, "")

    def _extract_cr_point_info(self, point) -> Optional[dict]:
        """
        统一解析 CRPoint（对象或to_dict后的dict）：
        返回：{type:'C'/'R', dt:datetime, date_str:'YYYY-MM-DD', open_price:float|None}
        """
        try:
            if point is None:
                return None

            if isinstance(point, dict):
                pt = point.get("pointType") or point.get("point_type") or ""
                td = point.get("triggerDate") or point.get("trigger_date")
                op = point.get("openPrice") or point.get("open_price") or point.get("open")
            else:
                pt = getattr(point, "point_type", "") or ""
                td = getattr(point, "trigger_date", None)
                op = getattr(point, "open_price", None)

            pt_u = str(pt).upper()
            norm_type = "C" if pt_u.startswith("C") else ("R" if pt_u.startswith("R") else None)
            if norm_type is None:
                return None

            dt = None
            if isinstance(td, str):
                try:
                    dt = datetime.strptime(td.split(" ")[0], "%Y-%m-%d")
                except Exception:
                    dt = None
            elif hasattr(td, "strftime"):
                dt = td
            if not dt:
                return None

            date_str = dt.strftime("%Y-%m-%d")
            open_price = None
            try:
                if op is not None:
                    open_price = float(op)
            except Exception:
                open_price = None

            return {"type": norm_type, "dt": dt, "date_str": date_str, "open_price": open_price}
        except Exception:
            return None

    def _get_support_price_actual(self, stock_code: str, date_str: str) -> Optional[float]:
        """取某日支撑位（daily_chance.support_price / 100），取不到返回None。"""
        try:
            dc = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            sp = getattr(dc, "support_price", None) if dc else None
            if not sp or sp <= 0:
                return None
            return float(sp) / 100.0
        except Exception:
            return None

    def _get_daily_open(self, stock_code: str, date_str: str) -> Optional[float]:
        """取某日开盘价（daily.open），取不到返回None。"""
        try:
            d = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            op = getattr(d, "open", None) if d else None
            if op is None:
                return None
            return float(op)
        except Exception:
            return None

    def _get_kline_date_index_map(self, kline_data: list) -> dict:
        """
        为当前 kline_data 构建 date_str->index 映射（缓存到 service 实例，避免在循环里反复O(N)构建）
        兼容 DomainKLineData / SimpleNamespace / dict（time/date字段）。
        """
        key = id(kline_data)
        if self._kline_date_index_cache_key == key and isinstance(self._kline_date_index_cache, dict):
            return self._kline_date_index_cache

        m = {}
        for i, k in enumerate(kline_data or []):
            try:
                t = None
                if isinstance(k, dict):
                    t = k.get("time") or k.get("date")
                else:
                    t = getattr(k, "time", None)
                if isinstance(t, str):
                    dt = datetime.strptime(t.split(" ")[0], "%Y-%m-%d")
                elif hasattr(t, "strftime"):
                    dt = t
                else:
                    continue
                m[dt.strftime("%Y-%m-%d")] = i
            except Exception:
                continue

        self._kline_date_index_cache_key = key
        self._kline_date_index_cache = m
        return m

    def _get_ma20_by_date_str(self, ma20_list: list, kline_data: list, date_str: str) -> Optional[float]:
        """按日期取MA20（依赖kline_data与ma20_list对齐）。"""
        try:
            idx_map = self._get_kline_date_index_map(kline_data)
            idx = idx_map.get(date_str)
            if idx is None:
                return None
            if idx < 0 or idx >= len(ma20_list):
                return None
            v = ma20_list[idx]
            return float(v) if v is not None else None
        except Exception:
            return None
    
    def _check_deviation(self, stock_code: str, date: datetime,
                         ma_data: Optional[dict] = None,
                         current_index: Optional[int] = None) -> RPointPluginResult:
        """
        插件1: 乖离率偏离
        
        包含7个子条件：
        1. 连续2个以上涨停
        2. 前3日累计涨幅过大
        3. 前5日累计涨幅过大
        4. 连续5连阳+阶段涨幅过大
        5. 前15日累计涨幅过大
        6. 前20日累计涨幅过大
        7. 当日收盘价相对MA10偏离>15%（主板）/>25%（非主板）
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
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 获取当日daily_chance（成交量类型、空头组合）
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_chance:
                current_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            
            # 如果没有daily_chance数据，无法判断成交量和空头组合，记录日志
            if not current_chance:
                logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 无daily_chance数据，跳过检查")
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 获取历史数据（提前获取，供 Condition 8 和后续使用）
            # 需要至少21个前序交易日，用于“前20日+1”基准价（Condition 6）
            # 虽然 Condition 8 只需要 5-6 天，但统一下载避免重复
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            
            # 获取前N日数据
            prev_data_list = []
            if prev_dates:
               for prev_date in prev_dates[:25]:
                   data = self._daily_cache.get(prev_date)
                   if not data:
                       data = self.daily_repo.find_by_date(stock_code, prev_date)
                   if data:
                       prev_data_list.append(data)
            
            stock_nature = current_chance.stock_nature or "波段"

            # 子条件8（优先检查）：前5日涨幅过大（20%/25%）或（5连阳+涨幅过大）+（G型放量+大阴线 或 2日阴+累计跌幅>6%）
            # 仅针对短线/波段股。如果是短线股，此条件可豁免"前置条件(阳线)"检查，因此放在由于。
            if stock_nature in ["短线", "波段"]:
                if len(prev_data_list) >= 5:
                    prev_1_day = prev_data_list[0] # T-1
                    prev_5_day = prev_data_list[4] # T-5
                    base_price = None
                    if len(prev_data_list) >= 6:
                        base_price = prev_data_list[5].close # T-6 收盘
                    elif prev_5_day.open and prev_5_day.open > 0:
                        base_price = prev_5_day.open # T-5 开盘
                    
                    hist_rise_ok = False
                    if prev_1_day.close and prev_1_day.close > 0 and base_price and base_price > 0:
                        gain_5d = (prev_1_day.close - base_price) / base_price * 100
                        thresh_5d = 20.0 if is_main_board else 25.0
                        
                        # A. 单纯涨幅达标
                        if gain_5d > thresh_5d:
                            hist_rise_ok = True
                        # B. 5连阳 + 涨幅达标
                        else:
                            all_red = True
                            for i in range(5):
                                d = prev_data_list[i]
                                if d.close < d.open:
                                    all_red = False
                                    break
                            if all_red and gain_5d > thresh_5d:
                                hist_rise_ok = True
                    
                    if hist_rise_ok:
                        reason_8 = ""
                        trigger_8 = False
                        
                        # 触发1：G型放量 + 今日大阴线
                        is_volume_g = self._check_volume_type(current_chance, ['G'])
                        if is_volume_g:
                            curr_close = current_data.close
                            curr_open = current_data.open
                            last_close = prev_1_day.close
                            if curr_close and curr_open and last_close:
                                drop_pct = (last_close - curr_close) / last_close * 100
                                body_pct = (curr_open - curr_close) / last_close * 100
                                if drop_pct > 5.0 and body_pct > 5.0:
                                    trigger_8 = True
                                    reason_8 = f"G型放量+大阴线(跌{drop_pct:.1f}%/实体{body_pct:.1f}%)"
                        
                        # 触发2：连续2日阴线（含今日）+ 累计跌幅>6%
                        if not trigger_8:
                            is_today_green = current_data.close < current_data.open
                            is_prev_green = prev_1_day.close < prev_1_day.open
                            
                            if is_today_green and is_prev_green:
                                if len(prev_data_list) >= 2:
                                    prev_2_day = prev_data_list[1]
                                    if prev_2_day.close and prev_2_day.close > 0:
                                        cum_drop = (prev_2_day.close - current_data.close) / prev_2_day.close * 100
                                        if cum_drop > 6.0:
                                            trigger_8 = True
                                            reason_8 = f"2连阴+累计跌幅{cum_drop:.1f}%"
                        
                        if trigger_8:
                            logger.info(f"[R点插件-乖离率偏离-条件8] {stock_code} {date_str} 触发: {reason_8}")
                            return RPointPluginResult("乖离率偏离", True, f"条件8: 前5日涨幅过大+{reason_8}")

            # 短线股前置条件检查：阳线 + 换手率 > 前一日 × 1.5 + 换手率 >= 9%
            # (如果上面条件8触发，则不会执行到这里；未触发则继续执行常规检查)
            if stock_nature == "短线":
                precondition_passed, precondition_reason = self._check_short_term_stock_precondition(
                    stock_code, date_str, current_data, stock_nature
                )
                if not precondition_passed:
                    logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 短线股前置条件未满足: {precondition_reason}")
                    return RPointPluginResult("乖离率偏离", False, "")


            
            # 预计算当日相对MA10的乖离度
            deviation = None
            if ma_data is not None and current_index is not None:
                ma10_list = ma_data.get('ma10')
                if ma10_list is not None and current_index < len(ma10_list):
                    ma10_today = ma10_list[current_index]
                    close_price = getattr(current_data, 'close', None)
                    if ma10_today is not None and ma10_today != 0 and close_price is not None:
                        deviation = (close_price - ma10_today) / ma10_today
            
            # 判断当日是否放量（XYH）或（XYZH）
            is_volume_xyz = self._check_volume_type(current_chance, ['X', 'Y', 'Z'])
            is_volume_xyh = self._check_volume_type(current_chance, ['X', 'Y', 'H'])
            is_volume_xyzh = self._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            
            # 判断当日K线形态
            matched_patterns = self._check_bearish_kline_patterns(current_data, stock_code)
            
            # 区分两类空头K线：
            # 1. 振幅>6%/8%的空头分歧K线（不包括阴线跌幅>3%/5%）
            # 2. 阴线跌幅>3%/5%（不需要振幅条件）
            bearish_patterns_with_amplitude = [p for p in matched_patterns if not p.startswith("阴线跌幅")]
            bearish_3pct_patterns = [p for p in matched_patterns if p.startswith("阴线跌幅")]
            
            is_bearish_kline_with_amplitude = len(bearish_patterns_with_amplitude) > 0  # 振幅>6%/8%的空头分歧K线
            is_bearish_3pct_line = len(bearish_3pct_patterns) > 0  # 阴线跌幅>3%/5%
            is_bearish_kline = len(matched_patterns) > 0  # 任意空头K线
            has_bearish_pattern = self._check_bearish_pattern(current_chance)  # 空头组合（从daily_chance）
            
            # 调试日志
            logger.debug(f"[R点-乖离率偏离] {stock_code} {date_str} 基础检查: volume_type={current_chance.volume_type}, "
                        f"is_volume_xyh={is_volume_xyh}, is_volume_xyzh={is_volume_xyzh}, "
                        f"is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                        f"is_bearish_3pct_line={is_bearish_3pct_line}, matched_patterns={matched_patterns}, "
                        f"has_bearish_pattern={has_bearish_pattern}")

            # 子条件7：当日收盘价相对MA10偏离，主板>15%，非主板>25%，且放量（XYH）且出现空头分歧K线（振幅>6%/8%）
            deviation_threshold = 0.15 if is_main_board else 0.25  # 主板15%，非主板25%
            if deviation is not None and deviation > deviation_threshold:
                if is_volume_xyh and is_bearish_kline_with_amplitude:
                    return RPointPluginResult(
                        "乖离率偏离",
                        True,
                        f"条件7: 收盘价偏离MA10 {deviation*100:.2f}%>{deviation_threshold*100:.0f}% 且放量XYH+空头分歧K线"
                    )
                else:
                    logger.debug(
                        f"[R点-乖离率偏离-条件7未达成] {stock_code} {date_str} deviation={deviation*100:.2f}% <= {deviation_threshold*100:.0f}%, "
                        f"is_volume_xyh={is_volume_xyh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}"
                    )

            # (历史数据获取代码已按需提前到前置条件检查之前，此处无需再次获取)
            
            if len(prev_data_list) < 6:
                return RPointPluginResult("乖离率偏离", False, "")
            
            # 计算涨跌幅：使用当前收盘价相对前一日收盘价（不依赖数据库涨跌幅字段）
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
                            f"is_volume_xyh={is_volume_xyh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                            f"is_bearish_3pct_line={is_bearish_3pct_line}, matched_patterns={matched_patterns}")
                # 条件1：放量(XYH) + (空头分歧K线振幅>6%/8% 或 阴线跌幅>3%/5%)
                if is_volume_xyh and (is_bearish_kline_with_amplitude or is_bearish_3pct_line):
                    amplitude = self._calculate_amplitude(current_data, stock_code)
                    if is_bearish_kline_with_amplitude:
                        pattern_desc = "、".join(bearish_patterns_with_amplitude)
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件1: 连续{consecutive_limits}个涨停+放量+空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                        )
                    else:
                        pattern_desc = "、".join(bearish_3pct_patterns)
                        return RPointPluginResult(
                            "乖离率偏离",
                            True,
                            f"条件1: 连续{consecutive_limits}个涨停+放量+{pattern_desc}"
                        )
            
            # === 条件2: 前3个交易日涨幅过大（昨日收盘相对前三日收盘，窗口需4日） ===
            if len(prev_data_list) >= 4:
                latest_close = prev_data_list[0].close  # 昨日
                prev_3_day = prev_data_list[3]         # 往前第3个交易日（如周一）
                if latest_close and latest_close > 0 and prev_3_day.close and prev_3_day.close > 0:
                    gain_3days = (latest_close - prev_3_day.close) / prev_3_day.close * 100
                    threshold_3days = 15 if is_main_board else 20
                    if gain_3days > threshold_3days:
                        logger.debug(f"[R点-乖离率偏离-条件2] {stock_code} {date_str} 前3日涨幅{gain_3days:.2f}%>{threshold_3days}%, "
                                    f"is_volume_xyh={is_volume_xyh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                                    f"is_bearish_3pct_line={is_bearish_3pct_line}")
                        if is_volume_xyh and (is_bearish_kline_with_amplitude or is_bearish_3pct_line):
                            amplitude = self._calculate_amplitude(current_data, stock_code)
                            if is_bearish_kline_with_amplitude:
                                pattern_desc = "、".join(bearish_patterns_with_amplitude)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件2: 前3日涨幅{gain_3days:.2f}%+放量+空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                                )
                            else:
                                pattern_desc = "、".join(bearish_3pct_patterns)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件2: 前3日涨幅{gain_3days:.2f}%+放量+{pattern_desc}"
                                )
            
            # === 条件3: 前5个交易日涨幅过大（昨日收盘相对前5日收盘，窗口需6日） ===
            if len(prev_data_list) >= 6:
                latest_close = prev_data_list[0].close  # 昨日
                prev_5_day = prev_data_list[5]          # 往前第5个交易日
                if latest_close and latest_close > 0 and prev_5_day.close and prev_5_day.close > 0:
                    gain_5days = (latest_close - prev_5_day.close) / prev_5_day.close * 100
                    threshold_5days = 20 if is_main_board else 25
                    if gain_5days > threshold_5days:
                        logger.debug(f"[R点-乖离率偏离-条件3] {stock_code} {date_str} 前5日涨幅{gain_5days:.2f}%>{threshold_5days}%, "
                                    f"is_volume_xyh={is_volume_xyh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                                    f"is_bearish_3pct_line={is_bearish_3pct_line}")
                        if is_volume_xyh and (is_bearish_kline_with_amplitude or is_bearish_3pct_line):
                            amplitude = self._calculate_amplitude(current_data, stock_code)
                            if is_bearish_kline_with_amplitude:
                                pattern_desc = "、".join(bearish_patterns_with_amplitude)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件3: 前5日涨幅{gain_5days:.2f}%+放量+空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                                )
                            else:
                                pattern_desc = "、".join(bearish_3pct_patterns)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件3: 前5日涨幅{gain_5days:.2f}%+放量+{pattern_desc}"
                                )
            
            # === 条件4: 连续5连阳+涨幅过大（昨日收盘相对前5日收盘，窗口需6日） ===
            if len(prev_data_list) >= 6:
                all_bullish = all(prev_data_list[i].close >= prev_data_list[i].open for i in range(5))
                latest_close = prev_data_list[0].close
                prev_5_day = prev_data_list[5]
                if all_bullish and latest_close and latest_close > 0 and prev_5_day.close and prev_5_day.close > 0:
                    gain_5days_yang = (latest_close - prev_5_day.close) / prev_5_day.close * 100
                    threshold_yang = 20 if is_main_board else 25
                    if gain_5days_yang > threshold_yang:
                        logger.debug(f"[R点-乖离率偏离-条件4] {stock_code} {date_str} 5连阳涨幅{gain_5days_yang:.2f}%>{threshold_yang}%, "
                                    f"is_volume_xyh={is_volume_xyh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                                    f"is_bearish_3pct_line={is_bearish_3pct_line}")
                        if is_volume_xyh and (is_bearish_kline_with_amplitude or is_bearish_3pct_line):
                            amplitude = self._calculate_amplitude(current_data, stock_code)
                            if is_bearish_kline_with_amplitude:
                                pattern_desc = "、".join(bearish_patterns_with_amplitude)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件4: 5连阳涨幅{gain_5days_yang:.2f}%+放量+空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                                )
                            else:
                                pattern_desc = "、".join(bearish_3pct_patterns)
                                return RPointPluginResult(
                                    "乖离率偏离",
                                    True,
                                    f"条件4: 5连阳涨幅{gain_5days_yang:.2f}%+放量+{pattern_desc}"
                                )
            
            # === 条件5: 前15个交易日涨幅>50%（昨日收盘相对前15日收盘，窗口需16日） ===
            if len(prev_data_list) >= 16:
                latest_close = prev_data_list[0].close
                prev_15_day = prev_data_list[15]
                if latest_close and latest_close > 0 and prev_15_day.close and prev_15_day.close > 0:
                    gain_15days = (latest_close - prev_15_day.close) / prev_15_day.close * 100
                    if gain_15days > 50:
                        logger.debug(f"[R点-乖离率偏离-条件5] {stock_code} {date_str} 前15日涨幅{gain_15days:.2f}%>50%, "
                                    f"is_volume_xyzh={is_volume_xyzh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                                    f"has_bearish_pattern={has_bearish_pattern}")
                        if is_volume_xyzh and (is_bearish_kline_with_amplitude or has_bearish_pattern):
                            amplitude = self._calculate_amplitude(current_data, stock_code)

                            signal_desc = ""
                            if is_bearish_kline_with_amplitude:
                                pattern_desc = "、".join(bearish_patterns_with_amplitude)
                                signal_desc = f"空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                            elif has_bearish_pattern:
                                bearish_patterns = current_chance.bearish_pattern.strip()
                                signal_desc = f"空头组合({bearish_patterns})"

                            return RPointPluginResult(
                                "乖离率偏离",
                                True,
                                f"条件5: 前15日涨幅{gain_15days:.2f}%+放量+{signal_desc}"
                            )
            
            # === 条件6: 前20个交易日涨幅>50%（昨日收盘相对前20日收盘，窗口需21日） ===
            if len(prev_data_list) >= 21:
                latest_close = prev_data_list[0].close
                prev_20_day = prev_data_list[20]
                if latest_close and latest_close > 0 and prev_20_day.close and prev_20_day.close > 0:
                    gain_20days = (latest_close - prev_20_day.close) / prev_20_day.close * 100
                    if gain_20days > 50:
                        logger.debug(f"[R点-乖离率偏离-条件6] {stock_code} {date_str} 前20日涨幅{gain_20days:.2f}%>50%, "
                                    f"is_volume_xyzh={is_volume_xyzh}, is_bearish_kline_with_amplitude={is_bearish_kline_with_amplitude}, "
                                    f"has_bearish_pattern={has_bearish_pattern}")
                        if is_volume_xyzh and (is_bearish_kline_with_amplitude or has_bearish_pattern):
                            amplitude = self._calculate_amplitude(current_data, stock_code)

                            signal_desc = ""
                            if is_bearish_kline_with_amplitude:
                                pattern_desc = "、".join(bearish_patterns_with_amplitude)
                                signal_desc = f"空头分歧K线({pattern_desc},振幅{amplitude:.2f}%)"
                            elif has_bearish_pattern:
                                bearish_patterns = current_chance.bearish_pattern.strip()
                                signal_desc = f"空头组合({bearish_patterns})"

                            return RPointPluginResult(
                                "乖离率偏离",
                                True,
                                f"条件6: 前20日涨幅{gain_20days:.2f}%+放量+{signal_desc}"
                            )
            



            return RPointPluginResult("乖离率偏离", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-乖离率偏离检查失败: {e}")
            return RPointPluginResult("乖离率偏离", False, "")
    
    def _check_pressure_stagnation(
        self,
        stock_code: str,
        date: datetime,
        c_point_date: Optional[datetime] = None,
        last_valid_point_type: Optional[str] = None,
        macd_data: Optional[dict] = None,
        current_index: Optional[int] = None,
        historical_c_points: Optional[list] = None,
        historical_r_points: Optional[list] = None,
    ) -> RPointPluginResult:
        """
        插件2: 临近压力位滞涨（重写版）
        
        新规则分两种：
        1）临近压力位 + 放量 + 风险K线
        2）临近压力位 + 前两日放量 + 风险K线
        
        公共前置（优化版，后续情形1-4条件不变）：
        - 必须“上一个有效点”为C（由上层传入 c_point_date + last_valid_point_type）
        - 分两种场景：
          A）仅一个C：往前是C且再往前是R
             - 用“今日前一日压力位” vs “发C日压力位”比较：
               - 若 C压力位 > 今日前一日压力位 => 不满足
               - 若 C压力位 <= 今日前一日压力位 => 继续后续逻辑
             - 若 C日无压力位（0/空）：统计“发C日 → 今日”的涨幅，若 >15% 视为压力位有效，继续后续逻辑
          B）多个C：上个是C、上上也是C、再往前是R（即：上个R之后出现连续多个C）
             - 取“离R点最近的第一个C”的压力位，与“今日前一日压力位”对比：必须相同
             - 若相同，再判断空间阈值 ≥15%：
               空间阈值 = (今日前一日压力位 - firstC支撑位) / firstC支撑位
        - 前一交易日赔率 > 0
        - 距离压力线：0% < (压力线-今日收盘)/今日收盘 < 距离阈值（主/非主一致，可配置）
        
        情形1（放量当日）：
        - 当日放量（XYZH）
        - 当日风险K线任一：
            振幅>6%/8%的 冲高回落阳/阴线、冲高回落阳/阴十字星、高开低走
            或 跌幅>3%（主板）/5%（非主板）的阴线
        
        情形2（前两日放量，当日未放量）：
        - 当日未放量（无XYZH），但满足风险K线集：冲高回落阴线、冲高回落阳线、高开低走、乌云盖顶（空头组合命中）
        - 再往前看2个交易日（即最近两日均满足距离压力线 <8%）
        - 前两日任意一日出现过放量（XYZH）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
            amplitude_threshold = 6 if is_main_board else 8
            decline_threshold = 3 if is_main_board else 5
            distance_threshold = self.config_service.get_pressure_stagnation_distance_threshold() or 8.0
            
            # 当日数据
            current_data = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 当前 daily_chance
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 前一交易日数据（赔率、压力线用）
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            if not prev_dates or len(prev_dates) < 1:
                return RPointPluginResult("临近压力位滞涨", False, "")
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            prev_data = self._daily_cache.get(prev_date_str) or self.daily_repo.find_by_date(stock_code, prev_date_str)
            if not prev_chance or not prev_data:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 回溯最近C点：由上层传入最近C点和最近有效点类型
            if not c_point_date or last_valid_point_type != 'C':
                return RPointPluginResult("临近压力位滞涨", False, "")

            if not prev_chance.pressure_price:
                return RPointPluginResult("临近压力位滞涨", False, "")
            prev_pressure = prev_chance.pressure_price / 100.0

            # ========= 公共前置：单C vs 多C =========
            # 默认按“单C”处理；若上层传入了历史点序列，则按真实信号序列判断“单C/多C”。
            c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else str(c_point_date)

            # 解析今日之前的有效点序列（C/R），用于判断“上个R之后是1个C还是多个C”
            points = []
            if historical_c_points or historical_r_points:
                for p in (historical_c_points or []) + (historical_r_points or []):
                    info = self._extract_cr_point_info(p)
                    if not info:
                        continue
                    if info.get("dt") and info["dt"] < date:
                        points.append(info)
                points.sort(key=lambda x: x["dt"])

            # 尝试以历史序列修正“当前最近C日期”（避免上层 c_point_date 与序列末端不一致）
            if points and points[-1].get("type") == "C":
                c_date_str = points[-1].get("date_str") or c_date_str

            # 判定是否多C：上个是C、上上也是C、再往前是R
            multi_c_mode = False
            first_c_after_r_date_str = None
            if points and len(points) >= 3 and points[-1].get("type") == "C":
                if points[-2].get("type") == "C":
                    j = len(points) - 2
                    while j >= 0 and points[j].get("type") == "C":
                        j -= 1
                    if j >= 0 and points[j].get("type") == "R":
                        # 连续C序列：points[j+1 ... end]
                        multi_c_mode = True
                        first_c_after_r_date_str = points[j + 1].get("date_str")

            if multi_c_mode and first_c_after_r_date_str:
                # 多C：对齐 firstC 压力位 == 今日前一日压力位；且空间阈值 >=15%
                first_c_chance = self._daily_chance_cache.get(first_c_after_r_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, first_c_after_r_date_str)
                first_c_pressure = (first_c_chance.pressure_price / 100.0) if (first_c_chance and getattr(first_c_chance, "pressure_price", None)) else 0
                if not first_c_pressure or first_c_pressure <= 0:
                    return RPointPluginResult("临近压力位滞涨", False, "")

                # “是否相同”按严格相等 + 微小误差容忍
                if abs(first_c_pressure - prev_pressure) > 1e-6:
                    return RPointPluginResult("临近压力位滞涨", False, "")

                first_c_support = self._get_support_price_actual(stock_code, first_c_after_r_date_str)
                if not first_c_support or first_c_support <= 0:
                    return RPointPluginResult("临近压力位滞涨", False, "")

                space_pct = (prev_pressure - first_c_support) / first_c_support * 100
                if space_pct < 15.0:
                    return RPointPluginResult("临近压力位滞涨", False, "")
            else:
                # 单C：用发C日压力位与今日前一日压力位比较；若C日无压力位则用“发C日→今日”涨幅>15%兜底
                c_chance = self._daily_chance_cache.get(c_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, c_date_str)
                c_pressure = (c_chance.pressure_price / 100.0) if (c_chance and getattr(c_chance, "pressure_price", None)) else 0

                if c_pressure and c_pressure > 0:
                    if c_pressure > prev_pressure:
                        return RPointPluginResult("临近压力位滞涨", False, "")
                else:
                    # 无压力位：统计发C日至今涨幅 >15%
                    c_data = self._daily_cache.get(c_date_str) or self.daily_repo.find_by_date(stock_code, c_date_str)
                    if not c_data or not getattr(c_data, "close", None) or c_data.close <= 0:
                        return RPointPluginResult("临近压力位滞涨", False, "")
                    gain_from_c = (current_data.close - c_data.close) / c_data.close * 100
                    if gain_from_c <= 15.0:
                        return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 前一日赔率>0
            day_win_ratio_score = prev_chance.day_win_ratio_score or 0
            if day_win_ratio_score <= 0:
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 距离压力线固定阈值8%
            distance_pct = (prev_pressure - current_data.close) / current_data.close * 100
            if not (0 < distance_pct < distance_threshold):
                return RPointPluginResult("临近压力位滞涨", False, "")
            
            # 风险K线判定
            def is_risk_kline(data) -> bool:
                pattern = KLinePatternService.identify_pattern(stock_code, data.open, data.close, data.high, data.low, data.pre_close)
                amplitude = self._calculate_amplitude(data, stock_code)
                is_bearish = data.close < data.open
                risky_set = ["冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", "冲高回落阴十字星", "高开低走"]
                if pattern in risky_set and amplitude > amplitude_threshold:
                    return True
                if is_bearish:
                    decline = (data.close - data.open) / data.open * 100
                    if decline <= -decline_threshold:
                        return True
                return False
            
            # 情形1：当日放量+风险K线
            is_volume_today = self._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            if is_volume_today and is_risk_kline(current_data):
                return RPointPluginResult(
                    "临近压力位滞涨",
                    True,
                    f"临近压力位+放量+风险K线(距压{distance_pct:.2f}%,赔率{day_win_ratio_score:.1f})"
                )
            
            # 情形2：当日未放量，前两日任一天放量，前两日距离也在8%内，当日风险K线（含乌云盖顶空头组合）
            if not is_volume_today and len(prev_dates) >= 2:
                day1_str = prev_dates[0]
                day2_str = prev_dates[1]
                day1_data = self._daily_cache.get(day1_str) or self.daily_repo.find_by_date(stock_code, day1_str)
                day2_data = self._daily_cache.get(day2_str) or self.daily_repo.find_by_date(stock_code, day2_str)
                day1_chance = self._daily_chance_cache.get(day1_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, day1_str)
                day2_chance = self._daily_chance_cache.get(day2_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, day2_str)
                
                def dist_ok(data_day, chance_day):
                    if not data_day or not chance_day or not chance_day.pressure_price:
                        return False
                    p = chance_day.pressure_price / 100.0
                    d = (p - data_day.close) / data_day.close * 100
                    return 0 < d < distance_threshold
                
                day1_dist = dist_ok(day1_data, day1_chance)
                day2_dist = dist_ok(day2_data, day2_chance)
                has_volume_prev2 = (day1_chance and self._check_volume_type(day1_chance, ['X', 'Y', 'Z', 'H'])) or \
                                   (day2_chance and self._check_volume_type(day2_chance, ['X', 'Y', 'Z', 'H']))
                
                pattern_today = KLinePatternService.identify_pattern(stock_code, current_data.open, current_data.close, current_data.high, current_data.low, current_data.pre_close)
                amplitude_today = self._calculate_amplitude(current_data, stock_code)
                is_risk2 = False
                risk2_set = ["冲高回落阴线", "冲高回落阳线", "高开低走"]
                if pattern_today in risk2_set and amplitude_today > amplitude_threshold:
                    is_risk2 = True
                # 乌云盖顶（空头组合）
                if current_chance.bearish_pattern and "乌云盖顶" in current_chance.bearish_pattern:
                    is_risk2 = True
                
                if day1_dist and day2_dist and has_volume_prev2 and is_risk2:
                    return RPointPluginResult(
                        "临近压力位滞涨",
                        True,
                        f"临近压力位+前两日放量+风险K线(距压{distance_pct:.2f}%,赔率{day_win_ratio_score:.1f})"
                    )

            # 情形3：熊市 + 近3个交易日无AXYZ放量 + 当日空头组合（不看当日放量）
            # 仅在熊市生效
            market_type = self.config_service.get_market_type(date)
            if market_type == 'bear' and len(prev_dates) >= 3:
                prev3_dates = prev_dates[:3]  # 不含当日，向前3个交易日
                
                def has_target_volume(chance) -> bool:
                    return self._check_volume_type(chance, ['A', 'X', 'Y', 'Z'])
                
                prev3_chances = []
                for d in prev3_dates:
                    dc = self._daily_chance_cache.get(d) or self.daily_chance_repo.find_by_stock_and_date(stock_code, d)
                    if not dc:
                        prev3_chances = None
                        break
                    prev3_chances.append(dc)
                
                if prev3_chances:
                    no_ax_yz_prev3 = all(not has_target_volume(dc) for dc in prev3_chances)
                    has_bearish_today = self._check_bearish_pattern(current_chance)
                    
                    if no_ax_yz_prev3 and has_bearish_today:
                        return RPointPluginResult(
                            "临近压力位滞涨",
                            True,
                            f"熊市临近压力位+近3日无AXYZ放量+当日空头组合(距压{distance_pct:.2f}%,赔率{day_win_ratio_score:.1f})"
                        )

            # 情形4：当日空头组合 + 近5日出现MACD死叉（当日DIF<DEA且MACD<0）
            # 死叉定义：前一日MACD>0且DIF>DEA，当前日MACD<0且DIF<DEA
            if current_chance.bearish_pattern:
                def is_valid(v):
                    return v is not None

                # 优先使用外部传入的 MACD 序列（更稳定，且与策略2/其它插件使用同一套序列）
                if macd_data and current_index is not None:
                    dif_list = macd_data.get("dif") or []
                    dea_list = macd_data.get("dea") or []
                    macd_list = macd_data.get("macd") or []
                    if current_index < len(dif_list) and current_index < len(dea_list) and current_index < len(macd_list):
                        today_dif = dif_list[current_index]
                        today_dea = dea_list[current_index]
                        today_macd = macd_list[current_index]
                        if is_valid(today_dif) and is_valid(today_dea) and is_valid(today_macd) and today_dif < today_dea and today_macd < 0:
                            has_death_cross = False
                            cross_idx = None
                            start_i = max(1, current_index - 4)
                            for i in range(start_i, current_index + 1):
                                prev_i = i - 1
                                prev_macd = macd_list[prev_i]
                                prev_dif = dif_list[prev_i]
                                prev_dea = dea_list[prev_i]
                                cur_macd = macd_list[i]
                                cur_dif = dif_list[i]
                                cur_dea = dea_list[i]
                                if None in (prev_macd, prev_dif, prev_dea, cur_macd, cur_dif, cur_dea):
                                    continue
                                if prev_macd > 0 and prev_dif > prev_dea and cur_macd < 0 and cur_dif < cur_dea:
                                    has_death_cross = True
                                    cross_idx = i
                                    break
                            if has_death_cross:
                                return RPointPluginResult(
                                    "临近压力位滞涨",
                                    True,
                                    f"临压+当日空头组合+近5日MACD死叉(index={cross_idx})(当日DIF<DEA且MACD<0，距压{distance_pct:.2f}%,赔率{day_win_ratio_score:.1f})"
                                )

                # 降级：没有传入MACD序列时，用“足够长”的收盘价序列本地计算MACD，再在近5日内找死叉
                # 注意：MACD(12,26,9) 至少需要26个数据点，否则DIF/DEA会大量为None
                all_dates_desc = self._sorted_dates if self._sorted_dates else sorted(self._daily_cache.keys(), reverse=True)
                all_dates_asc = list(reversed(all_dates_desc))
                if date_str in all_dates_asc:
                    cur_pos = all_dates_asc.index(date_str)
                    # 取最多120个点（含当日），避免每次都算全量；同时确保>=26
                    start_pos = max(0, cur_pos - 119)
                    window_dates = all_dates_asc[start_pos:cur_pos + 1]

                    closes = []
                    valid = True
                    for d in window_dates:
                        data = self._daily_cache.get(d)
                        if not data:
                            data = self.daily_repo.find_by_date(stock_code, d)
                            if data:
                                self._daily_cache[d] = data
                        if not data or getattr(data, "close", None) is None:
                            valid = False
                            break
                        closes.append(float(data.close))

                    if valid and len(closes) >= 26:
                        macd_res = MACDService.calculate_macd(closes)
                        dif_list = macd_res.get('dif') or []
                        dea_list = macd_res.get('dea') or []
                        macd_list = macd_res.get('macd') or []

                        cur_idx = len(closes) - 1  # window内的当日索引
                        today_dif = dif_list[cur_idx] if cur_idx < len(dif_list) else None
                        today_dea = dea_list[cur_idx] if cur_idx < len(dea_list) else None
                        today_macd = macd_list[cur_idx] if cur_idx < len(macd_list) else None

                        # 当日状态：DIF<DEA 且 MACD<0
                        if is_valid(today_dif) and is_valid(today_dea) and is_valid(today_macd) and (today_dif < today_dea) and (today_macd < 0):
                            has_death_cross = False
                            cross_idx = None
                            # 在“近5个交易日（含当日）”窗口内找死叉转换点
                            start_i = max(1, cur_idx - 4)
                            for i in range(start_i, cur_idx + 1):
                                prev_i = i - 1
                                prev_macd = macd_list[prev_i] if prev_i < len(macd_list) else None
                                prev_dif = dif_list[prev_i] if prev_i < len(dif_list) else None
                                prev_dea = dea_list[prev_i] if prev_i < len(dea_list) else None
                                cur_macd = macd_list[i] if i < len(macd_list) else None
                                cur_dif = dif_list[i] if i < len(dif_list) else None
                                cur_dea = dea_list[i] if i < len(dea_list) else None

                                if None in (prev_macd, prev_dif, prev_dea, cur_macd, cur_dif, cur_dea):
                                    continue
                                if prev_macd > 0 and prev_dif > prev_dea and cur_macd < 0 and cur_dif < cur_dea:
                                    has_death_cross = True
                                    cross_idx = i
                                    break

                            if has_death_cross:
                                cross_date = window_dates[cross_idx] if cross_idx is not None and 0 <= cross_idx < len(window_dates) else None
                                return RPointPluginResult(
                                    "临近压力位滞涨",
                                    True,
                                    f"临压+当日空头组合+近5日MACD死叉({cross_date or '-'})(当日DIF<DEA且MACD<0，距压{distance_pct:.2f}%,赔率{day_win_ratio_score:.1f})"
                                )
            
            return RPointPluginResult("临近压力位滞涨", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-临近压力位滞涨检查失败: {e}")
            return RPointPluginResult("临近压力位滞涨", False, "")
    
    def _check_bear_market_test(self, stock_code: str, date: datetime,
                               c_point_date: Optional[datetime] = None,
                               last_valid_point_type: Optional[str] = None,
                               last_c_point_type: Optional[str] = None) -> RPointPluginResult:
        """
        测试插件：熊市且当日股价>0 则直接触发R点，用于前端tooltip验证
        额外输出：最近C点日期 + 上一个信号类型
        """
        try:
            market_type = self.config_service.get_market_type(date)
            if market_type != 'bear':
                return RPointPluginResult("熊市测试R", False, "")
            
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            current_data = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data or not current_data.close or current_data.close <= 0:
                return RPointPluginResult("熊市测试R", False, "")

            c_date_str = None
            if c_point_date:
                if isinstance(c_point_date, datetime):
                    c_date_str = c_point_date.strftime('%Y-%m-%d')
                else:
                    c_date_str = str(c_point_date)

            last_sig = last_valid_point_type or "-"
            last_c_src = "-"
            if last_c_point_type:
                if str(last_c_point_type).upper() == 'C_STRATEGY2':
                    last_c_src = "C_STRATEGY2(S2)"
                elif str(last_c_point_type).upper() == 'C':
                    last_c_src = "C(S1)"
                else:
                    last_c_src = str(last_c_point_type)
            
            reason = f"熊市测试R: market_type=bear, close={current_data.close:.2f}>0, lastC={c_date_str or '-'}, lastSig={last_sig}, lastCSource={last_c_src}"
            return RPointPluginResult("熊市测试R", True, reason)
        except Exception as e:
            logger.error(f"R点插件-熊市测试R检查失败: {e}")
            return RPointPluginResult("熊市测试R", False, "")
    
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
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
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
    
    def _check_weak_breakout(self, stock_code: str, date: datetime, c_point_date: datetime,
                             last_valid_point_type: Optional[str] = None) -> RPointPluginResult:
        """
        插件4: 上冲乏力（现改为仅熊市生效）
        
        条件:
        - 仅在熊市生效
        - 最近有效信号必须是C（不是R），且传入了C点日期
        - 从发C日（最低价）到今日收盘累计涨幅 > 15%
        - 使用“今日前一交易日”的压力线：要求存在压力线且赔率>0
        - 当前股价距压力线：0% < (压力线-今日收盘)/今日收盘 < 距离阈值（与“临近压力位滞涨”一致，可配置，默认10%）
        - 前一日涨幅 ≥ 6%（主板）/ ≥8%（非主板）
        - 今日放量（A/X/Y/Z/H 任一）
        - 今日K线满足风险形态之一：
            * 振幅>6%/8%的 冲高回落阳/阴线
            * 振幅>6%/8%的 冲高回落阳/阴十字星
            * 振幅>6%/8%的 高开低走
            * 阴线跌幅 >3%（主板）/>5%（非主板）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else c_point_date
            
            # 仅熊市生效
            market_type = self.config_service.get_market_type(date)
            if market_type != 'bear':
                return RPointPluginResult("上冲乏力", False, "")

            # 必须最近有效信号是C
            if last_valid_point_type != 'C':
                return RPointPluginResult("上冲乏力", False, "")

            # 判断主板还是非主板（统一规则）
            is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
            
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
            
            # 计算从C点“最低价”到今日收盘的累计涨幅
            cumulative_gain = ((current_data.close - c_data.low) / c_data.low * 100) if c_data.low else 0
            
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
            
            # 获取前一交易日数据，使用前一交易日的赔率得分/压力线
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            if len(prev_dates) < 1:
                return RPointPluginResult("上冲乏力", False, "")
            
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            if not prev_chance:
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查前一交易日的赔率（根据股性判断）
            # 要求：赔率得分不等于0，且小于阈值（同时用来判断“有压力线”）
            day_win_ratio_score = prev_chance.day_win_ratio_score or 0
            win_ratio_threshold = self._get_win_ratio_threshold_for_weak_breakout(stock_nature)
            
            if not (0 < day_win_ratio_score < win_ratio_threshold):
                return RPointPluginResult("上冲乏力", False, "")
            
            # 检查当前股价距离压力线的距离（阈值与“临近压力位滞涨”一致，可配置）
            distance_threshold = self.config_service.get_pressure_stagnation_distance_threshold() or 8.0
            if prev_chance.pressure_price and prev_chance.pressure_price > 0:
                close_price = current_data.close
                # 压力线价格需要除以100（数据库存储格式：1660代表16.60元）
                pressure_price_actual = prev_chance.pressure_price / 100.0
                distance_pct = (pressure_price_actual - close_price) / close_price * 100
                
                # 如果不在0%-阈值的范围内，不触发插件
                if not (0 < distance_pct < distance_threshold):
                    logger.debug(f"[上冲乏力] {stock_code} {date_str} 股价{close_price:.2f}距离压力线{pressure_price_actual:.2f}的距离{distance_pct:.2f}%不在0%-{distance_threshold}%范围内")
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
                amplitude = self._calculate_amplitude(current_data, stock_code)
                
                return RPointPluginResult(
                    "上冲乏力",
                    True,
                    f"熊市上冲乏力: 从C日低点涨幅{cumulative_gain:.2f}%"
                    f"+前日赔率(股性:{stock_nature},{day_win_ratio_score:.1f}<{win_ratio_threshold})"
                    f"+股价距压{distance_pct:.2f}%<{distance_threshold}%"
                    f"+昨日涨{yesterday_change:.2f}%"
                    f"+今日放量+空头K线({pattern_desc},振幅{amplitude:.2f}%)"
                )
            
            return RPointPluginResult("上冲乏力", False, "")
            
        except Exception as e:
            logger.error(f"R点插件-上冲乏力检查失败: {e}")
            return RPointPluginResult("上冲乏力", False, "")
    
    # ========== 辅助方法 ==========
    
    def _get_previous_trading_dates_from_cache(self, current_date_str, stock_code: str = None) -> List[str]:
        """
        获取前N个交易日的日期列表
        
        Args:
            current_date_str: 当前日期（字符串或datetime对象）
            stock_code: 股票代码，如果提供则从数据库查询真实交易日
        
        Returns:
            前N个交易日的日期列表（字符串格式）
        """
        try:
            # 确保 current_date_str 是字符串格式
            if isinstance(current_date_str, datetime):
                current_date_str = current_date_str.strftime('%Y-%m-%d')
            elif isinstance(current_date_str, date):
                current_date_str = current_date_str.strftime('%Y-%m-%d')
            
            # 首先从缓存获取（缓存初始化后只用内存，避免循环内回退查库）
            all_dates = self._sorted_dates if self._sorted_dates else sorted(self._daily_cache.keys(), reverse=True)
            result = []
            for date_str in all_dates:
                if date_str < current_date_str:
                    result.append(date_str)

            # 如果缓存未初始化（或缓存为空）才允许回退查询数据库交易日
            # 重要：在 analyze 接口中我们已做区间预加载，正常不应走到这里
            if (not self._daily_cache) and len(result) < 25 and stock_code:
                try:
                    # 从数据库查询前N个交易日
                    table_name = f"basic_data_{stock_code.lower()}"
                    from infrastructure.persistence.database import DatabaseConnection
                    
                    with DatabaseConnection.get_connection_context() as conn:
                        cursor = conn.cursor()
                        sql = f"""
                            SELECT DISTINCT DATE(shi_jian) as trade_date
                            FROM `{table_name}`
                            WHERE DATE(shi_jian) < %s
                              AND peroid_type = '1day'
                            ORDER BY trade_date DESC
                            LIMIT 25
                        """
                        cursor.execute(sql, (current_date_str,))
                        rows = cursor.fetchall()
                        
                        result = []
                        for row in rows:
                            if row[0]:
                                date_obj = row[0] if isinstance(row[0], date) else datetime.strptime(str(row[0]), '%Y-%m-%d').date()
                                result.append(date_obj.strftime('%Y-%m-%d'))
                except Exception as e:
                    logger.warning(f"从数据库查询交易日失败: {e}")

            return result
        except Exception as e:
            logger.error(f"获取前N个交易日失败: {e}")
            return []

    def _get_prev_close_from_cache(self, current_date_str: str) -> Optional[float]:
        """
        从缓存中获取某日期的前一交易日收盘价（不查数据库）。
        """
        try:
            if isinstance(current_date_str, datetime):
                current_date_str = current_date_str.strftime('%Y-%m-%d')
            elif isinstance(current_date_str, date):
                current_date_str = current_date_str.strftime('%Y-%m-%d')
            if not current_date_str:
                return None

            prev_dates = self._get_previous_trading_dates_from_cache(current_date_str)
            if not prev_dates:
                return None
            prev_data = self._daily_cache.get(prev_dates[0])
            if prev_data and getattr(prev_data, "close", 0) and prev_data.close > 0:
                return float(prev_data.close)
            return None
        except Exception:
            return None

    def _check_strong_to_weak_not_reversed(self, stock_code: str, date: datetime) -> RPointPluginResult:
        """
        插件：强转弱且未反转
        条件：
        - 前一日空头组合包含“强转弱”
        - 今日未修复：close < (前日收盘+前日开盘)/2
        - 今日成交量类型包含 G
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            if len(prev_dates) < 1:
                return RPointPluginResult("强转弱未反转", False, "")
            
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            prev_data = self._daily_cache.get(prev_date_str) or self.daily_repo.find_by_date(stock_code, prev_date_str)
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            current_data = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            
            if not prev_chance or not prev_data or not current_chance or not current_data:
                return RPointPluginResult("强转弱未反转", False, "")
            
            if not prev_chance.bearish_pattern or "强转弱" not in prev_chance.bearish_pattern:
                return RPointPluginResult("强转弱未反转", False, "")
            
            mid_prev = (prev_data.close + prev_data.open) / 2
            if current_data.close >= mid_prev:
                return RPointPluginResult("强转弱未反转", False, "")
            
            vol_today = current_chance.volume_type or ""
            vols = [v.strip() for v in vol_today.split(",") if v.strip()]
            if "G" not in vols:
                return RPointPluginResult("强转弱未反转", False, "")
            
            return RPointPluginResult(
                "强转弱未反转",
                True,
                f"前一日强转弱未修复，今日收盘<{mid_prev:.2f}，且G型放量({vol_today})"
            )
        except Exception as e:
            logger.error(f"R点插件-强转弱未反转检查失败: {e}")
            return RPointPluginResult("强转弱未反转", False, "")
    
    def _check_break_support(self, stock_code: str, date: datetime, c_point_date: Optional[datetime]) -> RPointPluginResult:
        """
        插件5: 跌破支撑位 (动态支撑)
        
        定义：
        收盘价 < 动态支撑位（MAX(前一日支撑, 上个C日支撑)）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 使用公共方法判断
            is_break, support_price, close_price, detail = self._is_break_dynamic_support(stock_code, date_str, c_point_date)
            
            if is_break:
                return RPointPluginResult(
                    "跌破支撑位",
                    True,
                    f"{detail}"
                )
            
            return RPointPluginResult("跌破支撑位", False, "")
        except Exception as e:
            logger.error(f"R点插件-跌破支撑位检查失败: {e}")
            return RPointPluginResult("跌破支撑位", False, "")

    def _check_high_position_r(self, stock_code: str, date: datetime, ma_data: dict, 
                               macd_data: dict, current_index: int, c_point_date: Optional[datetime] = None) -> RPointPluginResult:
        """
        插件6: 高位发R
        
        条件:
        1. 均线多头排列判断：
           - 当前是多头排列（5日>10日>20日>30日>60日），或
           - 前3个交易日出现过多头排列但当前不是多头排列
        2. 从当前往前20个交易日的最低价涨幅 > 18%
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
            # 从配置中获取涨幅阈值（默认18%）
            gain_threshold = self.config_service.get_high_position_gain_threshold()
            
            # 获取前20个交易日的数据
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
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
            
            # === 条件4: 跌破动态支撑位 ===
            is_break_support, _, _, break_detail = self._is_break_dynamic_support(
                stock_code, date_str, c_point_date, use_cache_only=True
            )
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

            # 新逻辑：如果死叉发生在之前5日内，需要今天仍处于DIF<DEA
            current_dif = dif_list[current_index] if current_index < len(dif_list) else None
            current_dea = dea_list[current_index] if current_index < len(dea_list) else None
            if None in [current_dif, current_dea]:
                return RPointPluginResult("高位发R", False, "")

            if death_cross_date != current_index and current_dif >= current_dea:
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
                     f"{break_detail}, "
                     f"MACD死叉")
            
            logger.info(f"[高位发R触发] {stock_code} {date_str}: {reason}")
            return RPointPluginResult("高位发R", True, reason)
            
        except Exception as e:
            logger.error(f"插件6-高位发R检查异常: {e}")
            return RPointPluginResult("高位发R", False, "")
    
    def _check_box_breakdown(self, stock_code: str, date: datetime, macd_data: dict, 
                            current_index: int, kline_data: list, c_point_date: Optional[datetime] = None) -> RPointPluginResult:
        """
        插件7: 箱体回踩被跌破
        
        新逻辑:
        1. 从今天往前推20个交易日，找到最高价日X日，X日最高价距离今日当前价格 > 20%
        2. 从X日往前推22个交易日，查找是否有比X日更高的价格：
           - 如果有，确定该日为Y日
           - 找到这22天内的最低价日Z日
        3. 箱体确认：
           - 有Y日：Y日最高价 - Z日最低价 > 20%
           - 无Y日：X日最高价 - Z日最低价 > 20%
        4. 当前股价跌破动态支撑位
        5. MACD出现死叉（前5个交易日内）
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
            
            # === 步骤1: 找X日（今天往前20天的最高价所在日）===
            x_day_high = 0
            x_day_index = -1
            
            for i in range(current_index - 19, current_index + 1):
                if kline_data[i].high > x_day_high:
                    x_day_high = kline_data[i].high
                    x_day_index = i
            
            if x_day_index < 0:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 检查X日最高价距离当前价格 > 20%
            drop_ratio = (x_day_high - current_price) / x_day_high
            if drop_ratio <= 0.20:
                logger.debug(f"[箱体回踩] {stock_code} X日最高价{x_day_high:.2f}距当前{current_price:.2f}回落{drop_ratio*100:.2f}%不满足>20%")
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 步骤2: 从X日往前推22个交易日，找Y日和Z日 ===
            if x_day_index < 22:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 搜索范围：X-22 到 X-1（注意：不包括X日本身）
            box_start_index = x_day_index - 22
            box_end_index = x_day_index - 1
            
            # 找Y日：是否有比X日更高的价格
            y_day_high = None
            y_day_index = None
            y_day_date = None
            
            for i in range(box_start_index, box_end_index + 1):
                if kline_data[i].high > x_day_high:
                    if y_day_high is None or kline_data[i].high > y_day_high:
                        y_day_high = kline_data[i].high
                        y_day_index = i
                        y_day_date = kline_data[i].time.strftime('%Y-%m-%d')
            
            # 找Z日：这22天内的最低价
            z_day_low = None
            z_day_index = None
            z_day_date = None
            
            for i in range(box_start_index, box_end_index + 1):
                if z_day_low is None or kline_data[i].low < z_day_low:
                    z_day_low = kline_data[i].low
                    z_day_index = i
                    z_day_date = kline_data[i].time.strftime('%Y-%m-%d')
            
            # 检查数据有效性
            if z_day_low is None or z_day_low <= 0:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 步骤3: 箱体确认 ===
            if y_day_high is not None:
                # 有Y日：Y日最高价 - Z日最低价 > 20%
                box_gain_ratio = (y_day_high - z_day_low) / z_day_low
                if box_gain_ratio <= 0.20:
                    logger.debug(f"[箱体回踩] {stock_code} Y日{y_day_high:.2f}-Z日{z_day_low:.2f}涨幅{box_gain_ratio*100:.2f}%不满足>20%")
                    return RPointPluginResult("箱体回踩被跌破", False, "")
                box_high_price = y_day_high
                box_high_date = y_day_date
                has_y_day = True
            else:
                # 无Y日：X日最高价 - Z日最低价 > 20%
                box_gain_ratio = (x_day_high - z_day_low) / z_day_low
                if box_gain_ratio <= 0.20:
                    logger.debug(f"[箱体回踩] {stock_code} X日{x_day_high:.2f}-Z日{z_day_low:.2f}涨幅{box_gain_ratio*100:.2f}%不满足>20%")
                    return RPointPluginResult("箱体回踩被跌破", False, "")
                box_high_price = x_day_high
                box_high_date = kline_data[x_day_index].time.strftime('%Y-%m-%d')
                has_y_day = False
            
            # === 步骤4: 跌破动态支撑位 ===
            is_break_support, _, _, break_detail = self._is_break_dynamic_support(
                stock_code, date_str, c_point_date, use_cache_only=True
            )
            
            if not is_break_support:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 步骤5: MACD死叉（前5个交易日内出现）===
            dif_list = macd_data.get('dif', [])
            dea_list = macd_data.get('dea', [])
            
            if not dif_list or not dea_list or current_index >= len(dif_list) or current_index < 1:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # 检查前5个交易日内是否出现死叉（从金叉转为死叉）
            death_cross_found = False
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
                    death_cross_found = True
                    logger.debug(f"[箱体回踩] 在索引{check_index}发现死叉转换点")
                    break
            
            if not death_cross_found:
                return RPointPluginResult("箱体回踩被跌破", False, "")
            
            # === 全部条件满足，触发箱体回踩被跌破 ===
            x_day_date = kline_data[x_day_index].time.strftime('%Y-%m-%d')
            
            # 构建原因描述
            if has_y_day:
                reason = (f"X日({x_day_date})最高{x_day_high:.2f}, "
                         f"X-22日内找到更高Y日({y_day_date})最高{y_day_high:.2f}, "
                         f"Z日({z_day_date})最低{z_day_low:.2f}, "
                         f"Y-Z涨幅{box_gain_ratio*100:.1f}%, "
                         f"当前({current_price:.2f})较X日回落{drop_ratio*100:.1f}%, "
                         f"{break_detail}, "
                         f"MACD死叉")
            else:
                reason = (f"X日({x_day_date})最高{x_day_high:.2f}, "
                         f"Z日({z_day_date})最低{z_day_low:.2f}, "
                         f"X-Z涨幅{box_gain_ratio*100:.1f}%, "
                         f"当前({current_price:.2f})较X日回落{drop_ratio*100:.1f}%, "
                         f"{break_detail}, "
                         f"MACD死叉")
            
            logger.info(f"[箱体回踩被跌破触发] {stock_code} {date_str}: {reason}")
            return RPointPluginResult("箱体回踩被跌破", True, reason)
            
        except Exception as e:
            logger.error(f"插件7-箱体回踩被跌破检查异常: {e}")
            return RPointPluginResult("箱体回踩被跌破", False, "")
    
    def _check_downtrend_break_support(self, stock_code: str, date: datetime, ma_data: dict,
                                       macd_data: dict, current_index: int, kline_data: list,
                                       c_point_date: datetime) -> RPointPluginResult:
        """
        插件8: 趋势向下+未放量跌破支撑+MACD死叉
        
        条件:
        1. 低位C定义：上个C（不管哪个策略）当日收盘 < 当日MA60
        2. 跌破支撑：
           - 今日跌破前一交易日支撑位，或前三交易日已跌破支撑位（按“跌破前一日支撑”规则判定）
           - 或 当前股价跌破上个“低位C”当日的支撑位
        3. MACD：
           - 今日处于死叉状态（DIF < DEA）
           - 或 前三交易日内出现过死叉转换点（前一日DIF>DEA，当日DIF<DEA）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据
            current_data = self._daily_cache.get(date_str)
            if not current_data:
                current_data = self.daily_repo.find_by_date(stock_code, date_str)
            if not current_data:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")
            
            current_price = current_data.close

            # === 条件1: 上个C是否为“低位C”（上个C日收盘 < 上个C日MA60）===
            if not c_point_date:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

            low_c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else str(c_point_date)

            # 找到上个C在kline_data中的索引（从当前索引向前找，避免全量扫描）
            low_c_index = None
            for i in range(current_index, -1, -1):
                kt = getattr(kline_data[i], "time", None)
                if not kt:
                    continue
                kt_str = kt.strftime('%Y-%m-%d') if isinstance(kt, datetime) else str(kt)
                if kt_str == low_c_date_str:
                    low_c_index = i
                    break

            if low_c_index is None:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

            ma60_list = ma_data.get('ma60', [])
            if not ma60_list or low_c_index >= len(ma60_list):
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

            ma60_low_c = ma60_list[low_c_index]
            if ma60_low_c is None or ma60_low_c <= 0:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

            low_c_close = getattr(kline_data[low_c_index], "close", None)
            if low_c_close is None:
                low_c_data = self._daily_cache.get(low_c_date_str) or self.daily_repo.find_by_date(stock_code, low_c_date_str)
                low_c_close = getattr(low_c_data, "close", None) if low_c_data else None
            if low_c_close is None:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

            # 低位C门槛：上个C日收盘 < 上个C日MA60
            if float(low_c_close) >= float(ma60_low_c):
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")
            
            # === 条件2: 跌破支撑（近3日跌破前一日支撑 或 跌破上个低位C当日支撑）===
            break_support_recent_found = False
            break_support_recent_detail = None
            all_prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            check_dates = [date_str] + all_prev_dates[:3]  # 今日 + 前3个交易日
            
            # 【新逻辑】如果最近3个交易日内有C点（即 c_point_date 在 check_dates 中），
            # 则按照C当日的支撑线作为今天真实支撑线。如果不满足此条件，则走原有逻辑。
            c_date_in_range = False
            if c_point_date:
                c_date_str = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else str(c_point_date)
                # 检查 c_date_str 是否在 check_dates 范围内
                # check_dates 包含 [今天, 昨, 前, 大前]
                if c_date_str in check_dates:
                    c_date_in_range = True
                    # 获取C点当日支撑
                    c_chance = self._daily_chance_cache.get(c_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, c_date_str)
                    c_support_raw = getattr(c_chance, "support_price", None) if c_chance else None
                    if c_support_raw and c_support_raw > 0:
                        c_support_val = float(c_support_raw) / 100.0
                        if current_price < c_support_val:
                            break_support_recent_found = True
                            break_support_recent_detail = f"近3日有C({c_date_str})且今日收盘{current_price}跌破C日支撑{c_support_val}"
            
            if not c_date_in_range:
                # 原有逻辑：遍历检查每一天是否跌破了动态支撑
                for check_date_str in check_dates:
                    is_break_support, support_price_actual, check_close, detail = self._is_break_dynamic_support(
                        stock_code, check_date_str, c_point_date
                    )
                    if is_break_support:
                        break_support_recent_found = True
                        break_support_recent_detail = detail or (
                            f"{detail}"
                        )
                        break

            break_low_c_support_found = False
            break_low_c_support_detail = None
            low_c_chance = self._daily_chance_cache.get(low_c_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, low_c_date_str)
            low_c_support_raw = getattr(low_c_chance, "support_price", None) if low_c_chance else None
            if low_c_support_raw and low_c_support_raw > 0:
                low_c_support_actual = float(low_c_support_raw) / 100.0
                if current_price < low_c_support_actual:
                    break_low_c_support_found = True
                    break_low_c_support_detail = f"跌破上个低位C当日支撑({low_c_date_str}支撑{low_c_support_actual:.2f})"

            if not (break_support_recent_found or break_low_c_support_found):
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")
            
            # === 条件3: MACD当天死叉状态 或 前三交易日出现死叉转换点 ===
            dif_list = macd_data.get('dif', [])
            dea_list = macd_data.get('dea', [])
            
            if not dif_list or not dea_list or current_index >= len(dif_list) or current_index < 1:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")
            
            death_cross_ok = False
            death_cross_detail = None

            # 当天已处于死叉状态（DIF < DEA）
            curr_dif = dif_list[current_index]
            curr_dea = dea_list[current_index]
            if None not in [curr_dif, curr_dea] and curr_dif < curr_dea:
                death_cross_ok = True
                death_cross_detail = f"当日MACD死叉状态(DIF{curr_dif:.4f}<DEA{curr_dea:.4f})"
            else:
                # 检查前三交易日内是否出现死叉转换点
                start_check_index = max(1, current_index - 3)
                for check_index in range(start_check_index, current_index + 1):
                    if check_index <= 0:
                        continue

                    check_dif = dif_list[check_index]
                    check_dea = dea_list[check_index]
                    check_prev_dif = dif_list[check_index - 1]
                    check_prev_dea = dea_list[check_index - 1]

                    if None in [check_dif, check_dea, check_prev_dif, check_prev_dea]:
                        continue

                    if check_prev_dif > check_prev_dea and check_dif < check_dea:
                        death_cross_ok = True
                        death_cross_detail = f"前三日内死叉转换(索引{check_index})"
                        logger.debug(f"[趋势向下+未放量跌破支撑+MACD死叉] 在索引{check_index}发现死叉转换点")
                        break

            if not death_cross_ok:
                return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")
            
            # === 全部条件满足，触发R点 ===
            break_support_detail = break_support_recent_detail if break_support_recent_found else break_low_c_support_detail
            reason = (f"上个C({low_c_date_str})为低位C(收盘{float(low_c_close):.2f}<MA60{float(ma60_low_c):.2f}), "
                     f"{break_support_detail}, "
                     f"{death_cross_detail}")
            
            logger.info(f"[趋势向下+未放量跌破支撑+MACD死叉触发] {stock_code} {date_str}: {reason}")
            return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", True, reason)
            
        except Exception as e:
            logger.error(f"插件8-趋势向下+未放量跌破支撑+MACD死叉检查异常: {e}")
            return RPointPluginResult("趋势向下+未放量跌破支撑+MACD死叉", False, "")

    def _check_macd_long_dead_cross_break_support(self, stock_code: str, date: datetime,
                                                   macd_data: dict, current_index: int,
                                                   c_point_date: Optional[datetime] = None) -> RPointPluginResult:
        """
        插件11: MACD中长线死叉+跌破支撑（仅中长线股性）

        条件：
        - 股性：中长线
        - MACD死叉：今天往前3个交易日内出现 DIF 由上向下穿越 DEA
        - 成交量类型非空（任意类型即可）
        - 跌破前一日支撑：今日收盘 < 前一日支撑位（数据库存放100倍）
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date

            current_data = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_data or not current_chance:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            if len(prev_dates) < 1:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            prev_data = self._daily_cache.get(prev_date_str) or self.daily_repo.find_by_date(stock_code, prev_date_str)
            if not prev_chance or not prev_data:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            # 仅中长线
            stock_nature = getattr(current_chance, "stock_nature", None) or "波段"
            if stock_nature != "中长线":
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            # 成交量类型非空
            if not current_chance.volume_type:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            # MACD死叉：近3个交易日内，定义为：当日 DIF<DEA 且 MACD<0，前一日 MACD>0（红柱→蓝柱）
            dif_arr = macd_data.get('dif') if macd_data else None
            dea_arr = macd_data.get('dea') if macd_data else None
            macd_arr = macd_data.get('macd') if macd_data else None
            if not dif_arr or not dea_arr or not macd_arr:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            dead_cross = False
            start_idx = max(1, current_index - 2)
            end_idx = current_index
            for i in range(start_idx, end_idx + 1):
                if i >= len(dif_arr) or i >= len(dea_arr):
                    continue
                if dif_arr[i] is None or dea_arr[i] is None or dif_arr[i - 1] is None or dea_arr[i - 1] is None:
                    continue
                # 红柱→蓝柱且当日 DIF<DEA
                macd_prev = macd_arr[i - 1] if i - 1 < len(macd_arr) else None
                macd_curr = macd_arr[i] if i < len(macd_arr) else None
                if macd_prev is None or macd_curr is None:
                    continue
                if macd_prev > 0 and macd_curr < 0 and dif_arr[i] < dea_arr[i]:
                    dead_cross = True
                    break

            if not dead_cross:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            # 跌破动态支撑
            is_break, _, _, break_detail = self._is_break_dynamic_support(stock_code, date_str, c_point_date)
            if not is_break:
                return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

            reason = (
                f"中长线+MACD近3日死叉+量型({current_chance.volume_type})"
                f"+{break_detail}"
            )
            return RPointPluginResult("MACD中长线死叉+跌破支撑", True, reason)

        except Exception as e:
            logger.error(f"插件11-MACD中长线死叉+跌破支撑检查异常: {e}")
            return RPointPluginResult("MACD中长线死叉+跌破支撑", False, "")

    def _check_macd_long_top_divergence(self, stock_code: str, date: datetime,
                                        macd_data: dict, current_index: int, kline_data: list) -> RPointPluginResult:
        """
        插件12: 中长线顶背离（仅中长线股性）

        触发前置：
        - 仅股性为“中长线”
        - 当日满足：空头组合字段非空 或 三连阴（前天/昨天/今天均为阴线）

        回溯逻辑（从当前日向前）：
        1) 找到最近一次金叉G1（必须发生在今天之前；若最近一次交叉事件是死叉则不符合）
           定义：DIF从下方上穿DEA，且前一日蓝柱(MACD<0)、当日红柱(MACD>0)、当日DIF>DEA
        2) 找到G1之前最近一次死叉S1
           定义：DIF从上方下穿DEA，且前一日红柱(MACD>0)、当日蓝柱(MACD<0)、当日DIF<DEA
        3) 在S1之前找到最近的DIF局部高点H1，并取H1日最高价Price_H1
           定义：往前数10根K线，当日DIF与前一日DIF均大于再往前8个交易日的DIF
        4) 在G1之后、今天之前，找到DIF最大的日期H2，并取H2日最高价Price_H2
        5) 若 Price_H2 > Price_H1，则判定为“顶背离”，触发R
        """
        plugin_name = "中长线顶背离"
        try:
            # 基础数据检查
            if not macd_data or current_index is None or current_index <= 0:
                return RPointPluginResult(plugin_name, False, "")
            if not kline_data or current_index >= len(kline_data):
                return RPointPluginResult(plugin_name, False, "")

            dif_arr = macd_data.get('dif') if isinstance(macd_data, dict) else None
            dea_arr = macd_data.get('dea') if isinstance(macd_data, dict) else None
            macd_arr = macd_data.get('macd') if isinstance(macd_data, dict) else None
            if not dif_arr or not dea_arr or not macd_arr:
                return RPointPluginResult(plugin_name, False, "")
            if current_index >= len(dif_arr) or current_index >= len(dea_arr) or current_index >= len(macd_arr):
                return RPointPluginResult(plugin_name, False, "")

            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date)
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            if not current_chance:
                return RPointPluginResult(plugin_name, False, "")

            # 仅中长线
            stock_nature = getattr(current_chance, "stock_nature", None) or "波段"
            if stock_nature != "中长线":
                return RPointPluginResult(plugin_name, False, "")

            # 前置条件：空头组合 或 三连阴
            has_bearish_combo = self._check_bearish_pattern(current_chance)
            is_three_down = False
            if current_index >= 2:
                k0 = kline_data[current_index]
                k1 = kline_data[current_index - 1]
                k2 = kline_data[current_index - 2]
                try:
                    is_three_down = (k0.close < k0.open) and (k1.close < k1.open) and (k2.close < k2.open)
                except Exception:
                    is_three_down = False

            if not (has_bearish_combo or is_three_down):
                return RPointPluginResult(plugin_name, False, "")

            # ---------- Step 1: 最近一次交叉事件用于G1 ----------
            # 规则：从当前往前最多10个交易日逐日检查：
            #       若发现“前一日MACD<0 且 当日MACD>0”则视为金叉，取最近金叉为G1；
            #       若遇到死叉(前一日MACD>0 且 当日MACD<0)，继续向前扫描，不立即失败；
            #       超出10日仍未找到金叉则失败。
            g1_idx = None
            max_back = 10
            start_idx = max(1, current_index - max_back)
            for i in range(current_index - 1, start_idx - 1, -1):
                if i - 1 < 0:
                    break
                macd_prev, macd_curr = macd_arr[i - 1], macd_arr[i]
                if None in [macd_prev, macd_curr]:
                    continue

                is_gold = (macd_prev < 0) and (macd_curr > 0)
                is_dead = (macd_prev > 0) and (macd_curr < 0)

                if is_gold:
                    g1_idx = i
                    break
                # 如果是死叉，则继续向前找金叉（不立即失败）

            if g1_idx is None:
                return RPointPluginResult(plugin_name, False, "")

            # ---------- Step 2: G1之前最近死叉S1 ----------
            s1_idx = None
            for i in range(g1_idx - 1, 0, -1):
                if i - 1 < 0:
                    break
                dif_prev, dea_prev = dif_arr[i - 1], dea_arr[i - 1]
                dif_curr, dea_curr = dif_arr[i], dea_arr[i]
                macd_prev, macd_curr = macd_arr[i - 1], macd_arr[i]
                if None in [dif_prev, dea_prev, dif_curr, dea_curr, macd_prev, macd_curr]:
                    continue
                if (dif_prev > dea_prev) and (dif_curr < dea_curr) and (macd_prev > 0) and (macd_curr < 0) and (dif_curr < dea_curr):
                    s1_idx = i
                    break
            if s1_idx is None:
                return RPointPluginResult(plugin_name, False, "")

            # ---------- Step 3: S1之前最近DIF局部高点H1 ----------
            h1_idx = None
            for j in range(s1_idx - 1, 8, -1):  # 至少需要 j-9 >= 0
                if j - 9 < 0 or j - 1 < 0:
                    continue
                dif_j = dif_arr[j]
                dif_j1 = dif_arr[j - 1]
                if dif_j is None or dif_j1 is None:
                    continue
                prev8 = [dif_arr[j - k] for k in range(2, 10)]  # j-2..j-9
                if any(v is None for v in prev8):
                    continue
                m = max(prev8)
                if dif_j > m and dif_j1 > m:
                    h1_idx = j
                    break
            if h1_idx is None:
                return RPointPluginResult(plugin_name, False, "")

            try:
                price_h1 = float(getattr(kline_data[h1_idx], "high"))
            except Exception:
                return RPointPluginResult(plugin_name, False, "")
            dif_h1 = dif_arr[h1_idx]
            if dif_h1 is None:
                return RPointPluginResult(plugin_name, False, "")

            # ---------- Step 4: G1之后、今天之前，找 DIF 最大的日期H2 ----------
            # 说明：若Step1是在“最近为死叉后10日内找到金叉”，则以该金叉日G1为起点，
            #      在 (G1, today) 区间内直接取 DIF 最大的那一天作为H2（不再要求局部高点形态）。
            best_h2_idx = None
            best_h2_dif = None
            for j in range(g1_idx + 1, current_index):  # 排除今天
                if j < 0 or j >= len(dif_arr):
                    continue
                dif_j = dif_arr[j]
                if dif_j is None:
                    continue
                if best_h2_dif is None or dif_j > best_h2_dif or (dif_j == best_h2_dif and (best_h2_idx is None or j > best_h2_idx)):
                    best_h2_dif = dif_j
                    best_h2_idx = j

            if best_h2_idx is None:
                return RPointPluginResult(plugin_name, False, "")

            try:
                price_h2 = float(getattr(kline_data[best_h2_idx], "high"))
            except Exception:
                return RPointPluginResult(plugin_name, False, "")

            # ---------- Step 5: 价格创新高 + DIF降低 => 顶背离 ----------
            if not (price_h2 > price_h1):
                return RPointPluginResult(plugin_name, False, "")
            if best_h2_dif is None or not (best_h2_dif < dif_h1):
                return RPointPluginResult(plugin_name, False, "")

            t_g1 = getattr(kline_data[g1_idx], "time", None)
            t_s1 = getattr(kline_data[s1_idx], "time", None)
            t_h1 = getattr(kline_data[h1_idx], "time", None)
            t_h2 = getattr(kline_data[best_h2_idx], "time", None)
            t_g1s = self._to_date_str(t_g1) if t_g1 else f"idx{g1_idx}"
            t_s1s = self._to_date_str(t_s1) if t_s1 else f"idx{s1_idx}"
            t_h1s = self._to_date_str(t_h1) if t_h1 else f"idx{h1_idx}"
            t_h2s = self._to_date_str(t_h2) if t_h2 else f"idx{best_h2_idx}"

            precond = "空头组合" if has_bearish_combo else "三连阴"
            bearish_desc = ""
            if has_bearish_combo:
                try:
                    bearish_desc = f"({(current_chance.bearish_pattern or '').strip()})"
                except Exception:
                    bearish_desc = ""

            reason = (
                f"中长线+{precond}{bearish_desc}"
                f"+G1({t_g1s})+S1({t_s1s})"
                f"+H1({t_h1s},价高{price_h1:.2f},DIF{dif_h1:.4f})"
                f"+H2({t_h2s},价高{price_h2:.2f},DIF{best_h2_dif:.4f})"
                f"+价高创新高({price_h2:.2f}>{price_h1:.2f})且DIF降低({best_h2_dif:.4f}<{dif_h1:.4f})=>顶背离"
            )
            return RPointPluginResult(plugin_name, True, reason)

        except Exception as e:
            logger.error(f"插件12-中长线顶背离检查异常: {e}")
            return RPointPluginResult(plugin_name, False, "")

    def _check_high_stagnation_bearish(self, stock_code: str, date: datetime,
                                       ma_data: dict, macd_data: dict, current_index: int,
                                       c_point_date: Optional[datetime] = None) -> RPointPluginResult:
        """
        插件10: 高位滞涨
        
        1. 从当日往前“不含当日”5个交易日，找到最高价那日X
        2. 从X日向前推20个交易日，找到最低价Y
        3. 若X日最高价 > Y日最低价 * (1+配置阈值)，视为高位（默认15%）
        4. 满足高位后，同时出现以下任一组合即触发：
           A. 当日空头组合 + 跌破支撑
           B. 当日MACD已出现死叉（含前5日内） + 跌破支撑 + 当日MA5<=MA10
        """
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 获取当日数据及daily_chance（仅使用缓存，避免频繁IO）
            current_data = self._daily_cache.get(date_str)
            current_chance = self._daily_chance_cache.get(date_str)
            if not current_data or not current_chance:
                return RPointPluginResult("高位滞涨", False, "")
            
            current_price = current_data.close
            
            # ===== 步骤1：找到“近5个交易日(不含当日)”最高价日X =====
            all_dates = sorted(self._daily_cache.keys(), reverse=True)
            prev_dates = [d for d in all_dates if d < date_str]
            
            # 至少需要25个交易日数据：前5日找X（不含当日），再向前20日找Y
            if len(prev_dates) < 25:
                return RPointPluginResult("高位滞涨", False, "")
            
            check_dates = prev_dates[:5]  # 共5个交易日（不含当日）
            x_high = None
            x_date_str = None
            for d_str in check_dates:
                k = self._daily_cache.get(d_str)
                if not k or k.high is None:
                    return RPointPluginResult("高位滞涨", False, "")
                if x_high is None or k.high > x_high:
                    x_high = k.high
                    x_date_str = d_str
            
            if x_high is None or x_date_str is None:
                return RPointPluginResult("高位滞涨", False, "")
            
            # ===== 步骤2：从X日向前推20个交易日，找到最低价Y =====
            prev_before_x = [d for d in all_dates if d < x_date_str]
            if len(prev_before_x) < 20:
                return RPointPluginResult("高位滞涨", False, "")
            
            y_low = None
            y_date_str = None
            for d_str in prev_before_x[:20]:
                k = self._daily_cache.get(d_str)
                if not k or k.low is None:
                    return RPointPluginResult("高位滞涨", False, "")
                if y_low is None or k.low < y_low:
                    y_low = k.low
                    y_date_str = d_str
            
            if y_low is None or y_low <= 0:
                return RPointPluginResult("高位滞涨", False, "")
            
            # ===== 步骤3：高位条件（可配置阈值）=====
            gain_threshold_pct = self.config_service.get_high_stagnation_gain_threshold()
            gain_pct = (x_high - y_low) / y_low * 100
            if gain_pct <= gain_threshold_pct:
                return RPointPluginResult("高位滞涨", False, "")
            
            # ===== 支撑位检查（动态支撑）=====
            is_break_support, support_price_actual, current_close, break_detail = self._is_break_dynamic_support(
                stock_code, date_str, c_point_date, use_cache_only=True
            )
            if not is_break_support or support_price_actual is None or current_close is None:
                return RPointPluginResult("高位滞涨", False, "")
            
            # ===== 条件A：空头组合 + 跌破支撑 =====
            has_bearish_combo = self._check_bearish_pattern(current_chance)
            if has_bearish_combo:
                reason = (f"X日{self._to_date_str(x_date_str)}高点{x_high:.2f}, "
                          f"X-20日Y日{self._to_date_str(y_date_str)}低点{y_low:.2f}, "
                          f"涨幅{gain_pct:.2f}%>阈值{gain_threshold_pct:.2f}%, "
                          f"空头组合({current_chance.bearish_pattern.strip()})+{break_detail}")
                return RPointPluginResult("高位滞涨", True, reason)
            
            # ===== 条件B：MACD死叉（含前5日内）+跌破支撑+MA5<=MA10 =====
            dif_list = macd_data.get('dif', [])
            dea_list = macd_data.get('dea', [])
            if not dif_list or not dea_list or current_index >= len(dif_list) or current_index < 1:
                return RPointPluginResult("高位滞涨", False, "")
            
            death_cross_found = False
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
                if prev_dif > prev_dea and curr_dif < curr_dea:
                    death_cross_found = True
                    break
                if check_index == current_index and curr_dif < curr_dea:
                    death_cross_found = True
                    break
            
            if not death_cross_found:
                return RPointPluginResult("高位滞涨", False, "")
            
            # 增加 check: MA5 <= MA10
            ma5_list = ma_data.get('ma5', [])
            ma10_list = ma_data.get('ma10', [])
            if not ma5_list or not ma10_list or current_index >= len(ma5_list) or current_index >= len(ma10_list):
                 return RPointPluginResult("高位滞涨", False, "")
            
            ma5_val = ma5_list[current_index]
            ma10_val = ma10_list[current_index]
            if ma5_val is None or ma10_val is None:
                return RPointPluginResult("高位滞涨", False, "")
            
            if ma5_val > ma10_val:
                 return RPointPluginResult("高位滞涨", False, "")

            reason = (f"X日{self._to_date_str(x_date_str)}高点{x_high:.2f}, "
                      f"X-20日Y日{self._to_date_str(y_date_str)}低点{y_low:.2f}, "
                      f"涨幅{gain_pct:.2f}%>阈值{gain_threshold_pct:.2f}%, "
                      f"MACD死叉+MA5<=MA10+{break_detail}")
            return RPointPluginResult("高位滞涨", True, reason)
        
        except Exception as e:
            logger.error(f"插件10-高位滞涨检查异常: {e}")
            return RPointPluginResult("高位滞涨", False, "")
    
    def _is_break_dynamic_support(self, stock_code: str, check_date_str: str,
                                     c_point_date: Optional[datetime],
                                     use_cache_only: bool = False) -> Tuple[bool, Optional[float], Optional[float], Optional[str]]:
        """
        判断某日是否以收盘价跌破“动态支撑线”。
        动态支撑线规则：MAX(前一交易日支撑位, 上个C点日支撑位)
        
        Args:
            stock_code: 股票代码
            check_date_str: 检查日期（字符串）
            c_point_date: 上个C点日期（可选）
            use_cache_only: 是否仅使用缓存
            
        Returns:
            Tuple[bool, Optional[float], Optional[float], Optional[str]]:
                (是否跌破, 最终支撑价, 当日收盘价, 详情描述)
        """
        # 当日数据
        check_data = self._daily_cache.get(check_date_str)
        if not check_data and not use_cache_only:
            check_data = self.daily_repo.find_by_date(stock_code, check_date_str)
        if not check_data:
            return False, None, None, None
        
        check_close = check_data.close
        
        # 1. 获取前一交易日支撑位
        prev_support_val = 0.0
        prev_date_str = None
        
        prev_dates = self._get_previous_trading_dates_from_cache(check_date_str, stock_code)
        if prev_dates and len(prev_dates) > 0:
            prev_date_str = prev_dates[0]
            prev_chance = self._daily_chance_cache.get(prev_date_str)
            if not prev_chance and not use_cache_only:
                prev_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, prev_date_str)
            
            if prev_chance and prev_chance.support_price and prev_chance.support_price > 0:
                prev_support_val = float(prev_chance.support_price) / 100.0

        # 2. 获取C点日支撑位
        c_support_val = 0.0
        c_date_str_val = None
        
        if c_point_date:
            c_date_str_val = c_point_date.strftime('%Y-%m-%d') if isinstance(c_point_date, datetime) else str(c_point_date)
            # 只有当C点日期早于检查日期时才有效（防止未来数据或当天）
            # 不过通常C点都是之前的，这里简单判断一下
            if c_date_str_val < check_date_str:
                c_chance = self._daily_chance_cache.get(c_date_str_val)
                if not c_chance and not use_cache_only:
                    c_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, c_date_str_val)
                
                if c_chance and c_chance.support_price and c_chance.support_price > 0:
                    c_support_val = float(c_chance.support_price) / 100.0
        
        # 3. 比较并取最大值（动态支撑）
        # 只要有一个有效，就进行比较；如果都无效，则无法判断
        if prev_support_val <= 0 and c_support_val <= 0:
            return False, None, check_close, None
            
        final_support = max(prev_support_val, c_support_val)
        
        # 构造描述
        detail = ""
        if c_support_val > prev_support_val:
            detail = f"使用C日({c_date_str_val})支撑{c_support_val:.2f}(>前日{prev_support_val:.2f})"
        else:
            if c_support_val > 0:
                detail = f"使用前日({prev_date_str})支撑{prev_support_val:.2f}(>=C日{c_support_val:.2f})"
            else:
                detail = f"使用前日({prev_date_str})支撑{prev_support_val:.2f}(无C日支撑)"

        # 4. 判断跌破
        is_break = check_close < final_support
        
        if is_break:
            full_detail = f"跌破支撑({check_close:.2f}<{final_support:.2f}, {detail})"
            return True, final_support, check_close, full_detail
        else:
            return False, final_support, check_close, None
    
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

    def _calculate_amplitude(self, current_data, stock_code: str) -> float:
        """
        正确计算振幅：如果pre_close无效，从前一天数据获取收盘价作为基准

        Args:
            current_data: 当前日K线数据
            stock_code: 股票代码

        Returns:
            振幅百分比
        """
        # 首先尝试使用pre_close
        if current_data.pre_close and current_data.pre_close > 0:
            return ((current_data.high - current_data.low) / current_data.pre_close) * 100

        # 如果pre_close无效，优先从缓存获取前一日收盘价（避免循环内查库）
        prev_close = self._get_prev_close_from_cache(getattr(current_data, "date", None) or "")
        if prev_close and prev_close > 0:
            return ((current_data.high - current_data.low) / prev_close) * 100

        # 如果都失败了，使用开盘价作为基准（最后的后备方案）
        if current_data.open and current_data.open > 0:
            return ((current_data.high - current_data.low) / current_data.open) * 100

        return 0.0

    # ========== 辅助工具，防止缺失方法导致插件异常 ==========
    def _to_date_str(self, value) -> str:
        """统一日期转字符串，兼容datetime/date/str，缺省用str(value)。"""
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d')
        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        return str(value)

    # 关闭历史CR重算逻辑（性能考虑），插件2改为依赖上层传入的最近C/最近有效点类型
    
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
    
    def _get_turnover_rate(self, stock_code: str, date_str: str) -> Optional[float]:
        """
        获取换手率（huanshou）
        
        Args:
            stock_code: 股票代码
            date_str: 日期字符串 (YYYY-MM-DD)
            
        Returns:
            换手率百分比，如 9.5 表示 9.5%；查询失败返回 None
            
        Note:
            数据库中 huanshou 列存储的是小数形式，如 0.422 表示 0.422%
        """
        # 1) 先走进程内缓存（init_cache 已批量填充）
        try:
            if date_str in self._turnover_rate_cache:
                return self._turnover_rate_cache.get(date_str)
        except Exception:
            pass

        # 2) 再从 daily_chance_cache 补齐（避免缓存没初始化或某天缺失）
        try:
            dc = self._daily_chance_cache.get(date_str)
            if dc is not None:
                hs = getattr(dc, "huanshou", None)
                if hs is not None:
                    val = float(hs)
                    self._turnover_rate_cache[date_str] = val
                    return val
        except Exception:
            pass

        # 3) 懒加载兜底：只读库批量预取一次（只在确实缺失时触发，避免循环内N次建连/查询）
        try:
            if not self._turnover_prefetch_attempted:
                self._turnover_prefetch_attempted = True
                sc = self._turnover_prefetch_stock_code or stock_code
                sd = self._turnover_prefetch_start_date
                ed = self._turnover_prefetch_end_date
                if sc and sd and ed:
                    prefetched = self._prefetch_turnover_rates_from_readonly(sc, sd, ed)
                    if prefetched:
                        self._turnover_rate_cache.update(prefetched)
                        if date_str in self._turnover_rate_cache:
                            return self._turnover_rate_cache.get(date_str)
        except Exception as e:
            logger.debug(f"[换手率预取] {stock_code} {date_str} 懒加载失败: {e}")

        # 4) 最后兜底：只读库单次查询（应极少触发）
        try:
            conn = pymysql.connect(**READONLY_DB_CONFIG)
            try:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                sql = """
                    SELECT huanshou 
                    FROM b_daily_chance 
                    WHERE stock_code = %s AND DATE(date) = %s
                    LIMIT 1
                """
                cursor.execute(sql, (stock_code, date_str))
                row = cursor.fetchone()
                if row and row.get('huanshou') is not None:
                    # 数据库存储的是小数形式，如 0.422 表示 0.422%
                    # 直接返回该值作为百分比
                    val = float(row['huanshou'])
                    try:
                        self._turnover_rate_cache[date_str] = val
                    except Exception:
                        pass
                    return val
                return None
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[换手率查询] {stock_code} {date_str} 查询失败: {e}")
            return None

    def _prefetch_turnover_rates_from_readonly(self, stock_code: str, start_date: str, end_date: str) -> dict:
        """
        从只读库批量预取换手率，返回 {date_str: huanshou_float}。
        仅作为兜底：当本地 b_daily_chance 未填充 huanshou 时使用，避免循环内多次建连。
        """
        result = {}
        if not stock_code or not start_date or not end_date:
            return result
        conn = None
        try:
            conn = pymysql.connect(**READONLY_DB_CONFIG)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = """
                SELECT DATE(date) AS d, huanshou
                FROM b_daily_chance
                WHERE stock_code = %s AND date >= %s AND date <= %s
            """
            cursor.execute(sql, (stock_code, start_date, end_date))
            rows = cursor.fetchall() or []
            for row in rows:
                d = row.get("d")
                hs = row.get("huanshou")
                if d is None or hs is None:
                    continue
                try:
                    date_key = str(d)
                    result[date_key] = float(hs)
                except Exception:
                    continue
            if result:
                logger.info(f"[换手率预取] {stock_code} 命中 {len(result)} 条: {start_date}~{end_date}")
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        return result
    
    def _check_short_term_stock_precondition(
        self, 
        stock_code: str, 
        date_str: str, 
        current_data, 
        stock_nature: str
    ) -> Tuple[bool, str]:
        """
        检查短线股的前置条件（仅对股性为"短线"的股票生效）
        
        条件（必须同时满足）：
        1. 当日是阳线（收盘价 > 开盘价）
        2. 今日换手率 > 前一日换手率 × 1.5
        3. 今日换手率 >= 9%
        
        Args:
            stock_code: 股票代码
            date_str: 日期字符串
            current_data: 当日K线数据
            stock_nature: 股性
            
        Returns:
            (是否满足条件, 不满足的原因)
        """
        # 只对短线股生效
        if stock_nature != "短线":
            return True, ""
        
        # 条件1: 当日必须是阳线
        if not current_data or not current_data.close or not current_data.open:
            return False, "无法获取当日K线数据"
        
        if current_data.close <= current_data.open:
            return False, f"非阳线(收盘{current_data.close:.2f}<=开盘{current_data.open:.2f})"
        
        # 获取今日换手率
        today_turnover = self._get_turnover_rate(stock_code, date_str)
        if today_turnover is None:
            return False, "无法获取今日换手率"
        
        # 条件3: 今日换手率 >= 9%
        if today_turnover < 9.0:
            return False, f"今日换手率{today_turnover:.2f}%<9%"
        
        # 获取前一交易日
        prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
        if not prev_dates:
            return False, "无法获取前一交易日"
        
        prev_date_str = prev_dates[0]
        prev_turnover = self._get_turnover_rate(stock_code, prev_date_str)
        if prev_turnover is None:
            return False, f"无法获取前一日({prev_date_str})换手率"
        
        # 条件2: 今日换手率 > 前一日换手率 × 1.5
        threshold = prev_turnover * 1.5
        if today_turnover <= threshold:
            return False, f"今日换手率{today_turnover:.2f}%<=前一日{prev_turnover:.2f}%×1.5={threshold:.2f}%"
        
        logger.debug(f"[短线股前置条件] {stock_code} {date_str} 满足: "
                    f"阳线+今日换手率{today_turnover:.2f}%>前一日{prev_turnover:.2f}%×1.5且>=9%")
        return True, ""

    
    def _check_bearish_kline_patterns(self, daily_data, stock_code: str = None) -> List[str]:
        """
        检查所有空头K线形态，返回命中的形态列表
        
        Args:
            daily_data: 日K线数据
            stock_code: 股票代码（用于判断主板/非主板）
        
        Returns:
            命中的K线形态列表，如 ["冲高回落阳线", "高开低走"]
        """
        if not daily_data:
            return []
        
        matched_patterns = []
        
        # 判断主板还是非主板（统一规则）
        is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
        
        # 计算ABC
        O = daily_data.open
        C = daily_data.close
        H = daily_data.high
        L = daily_data.low
        
        # 获取前收价：优先使用pre_close；无效时仅从缓存补齐（不做DB回退，避免循环内SQL放大）
        prev_close = daily_data.pre_close if hasattr(daily_data, 'pre_close') else 0
        if not prev_close or prev_close == 0:
            if stock_code:
                try:
                    date_str = daily_data.date.strftime('%Y-%m-%d') if hasattr(daily_data.date, 'strftime') else str(daily_data.date)[:10]
                    prev_close_cached = self._get_prev_close_from_cache(date_str)
                    if prev_close_cached and prev_close_cached > 0:
                        prev_close = prev_close_cached
                except Exception as e:
                    logger.debug(f"[K线形态] 从缓存获取前收价失败: {e}")
                    return []
            else:
                return []  # 没有stock_code无法从缓存推断交易日顺序
        
        if prev_close == 0:
            logger.warning(f"[K线形态] 无法获取有效的前收价，跳过K线形态检测")
            return []  # 前收价无效
        
        # A: 上影线 = 最高价 - max(开盘价, 收盘价)
        A = H - max(O, C)
        # B: 实体 = abs(收盘价 - 开盘价)
        B = abs(C - O)
        # C: 下影线 = min(开盘价, 收盘价) - 最低价
        C_shadow = min(O, C) - L
        
        # 振幅门槛：主板6%，非主板8%
        amplitude_threshold = 6 if is_main_board else 8

        # 1. 冲高回落阳线（需要振幅>6%/8% -> 5% 临时调整）
        if self._check_bullish_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阳线")
        
        # 2. 冲高回落阴线（需要振幅>6%/8% -> 5% 临时调整）
        if self._check_bearish_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阴线")
        
        # 3. 冲高回落阳十字星（需要振幅>6%/8% -> 5% 临时调整）
        if self._check_bullish_doji_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阳十字星")
        
        # 4. 冲高回落阴十字星（需要振幅>6%/8% -> 5% 临时调整）
        if self._check_bearish_doji_high_fallback(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("冲高回落阴十字星")
        
        # 5. 高开低走（需要振幅>6%/8% -> 5% 临时调整）
        if self._check_high_open_low_close_new(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("高开低走")
        
        # 6. 高振幅阳十字星（需要振幅>8%/10%）
        if self._check_high_amplitude_bullish_doji(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("高振幅阳十字星")
        
        # 7. 高振幅阴十字星（需要振幅>8%/10%）
        if self._check_high_amplitude_bearish_doji(A, B, C_shadow, O, C, H, L, prev_close, is_main_board):
            matched_patterns.append("高振幅阴十字星")
        
        # 8. 阴线跌幅>3%/5%（相对开盘价）- 不需要振幅条件
        if self._check_bearish_line_3pct_new(O, C, prev_close, is_main_board):
            threshold_pct = 3 if is_main_board else 5
            matched_patterns.append(f"阴线跌幅>{threshold_pct}%")
        
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
        满足以下任一：
          - A = 0 且 C < 2B
          - A < 3B 且 C < 2B
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
        
        return (C < 2 * B and (A == 0 or A < 3 * B))
    
    def _check_bearish_line_3pct_new(self, O: float, close: float, prev_close: float, is_main_board: bool = True) -> bool:
        """
        阴线跌幅>3%/5%（相对开盘价）
        主板：跌幅 > 3%
        非主板（创业板/科创板）：跌幅 > 5%
        开盘价 > 收盘价（阴线）
        跌幅 = (收盘价 - 开盘价) / 开盘价 * 100
        """
        if O == 0:
            return False
        
        # 判断是否为阴线
        if O <= close:
            return False
        
        # 计算相对开盘价的跌幅
        change_pct = ((close - O) / O) * 100
        
        # 主板阈值3%，非主板阈值5%
        threshold = -3 if is_main_board else -5
        
        return change_pct < threshold
    
    def _check_high_amplitude_bullish_doji(self, A: float, B: float, C: float, O: float, close: float,
                                           H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        高振幅阳十字星
        振幅 > 8%（主板）或 10%（非主板）
        A > C（上影线 > 下影线）
        A > 3B（上影线 > 3倍实体）
        C > 2B（下影线 > 2倍实体）
        开盘价 < 收盘价（阳线）
        """
        if O >= close:  # 不是阳线
            return False
        if prev_close == 0:
            return False
        
        # 检查振幅（高振幅阈值：主板8%，非主板10%）
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 8 if is_main_board else 10
        if amplitude <= amplitude_threshold:
            return False
        
        return (A > C and 
                A > 3 * B and 
                C > 2 * B)
    
    def _check_high_amplitude_bearish_doji(self, A: float, B: float, C: float, O: float, close: float,
                                           H: float, L: float, prev_close: float, is_main_board: bool) -> bool:
        """
        高振幅阴十字星
        振幅 > 8%（主板）或 10%（非主板）
        A > C（上影线 > 下影线）
        A > 3B（上影线 > 3倍实体）
        C > 2B（下影线 > 2倍实体）
        开盘价 > 收盘价（阴线）
        """
        if O <= close:  # 不是阴线
            return False
        if prev_close == 0:
            return False
        
        # 检查振幅（高振幅阈值：主板8%，非主板10%）
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 8 if is_main_board else 10
        if amplitude <= amplitude_threshold:
            return False
        
        return (A > C and 
                A > 3 * B and 
                C > 2 * B)
    


    def _check_stage_rally_too_high(self, stock_code: str, date: datetime, ma_data: dict,
                                    macd_data: dict, current_index: int) -> RPointPluginResult:
        """
        插件: 阶段涨幅过大

        触发条件（同一天同时满足）：
        1) 从当日往前统计30个交易日涨幅 >= 30%
           - 取“今天往前的31个交易日”的收盘价作为起点（即 t-30 的收盘价）到今天收盘价的涨幅
        2) 今天出现任意成交量类型（daily_chance.volume_type 非空）
        3) 今天跌破MA20：昨天close > 昨天MA20 且 今天close < 今天MA20
        4) 今天MACD处于死叉状态：DIF < DEA
        """
        plugin_name = "阶段涨幅过大"
        try:
            date_str = self._to_date_str(date)

            # --- 今日/昨日数据 ---
            if current_index < 1:
                return RPointPluginResult(plugin_name, False, "")

            # 今日收盘
            current_daily = self._daily_cache.get(date_str) or self.daily_repo.find_by_date(stock_code, date_str)
            if not current_daily or not getattr(current_daily, "close", None):
                return RPointPluginResult(plugin_name, False, "")
            close_today = float(current_daily.close)
            if close_today <= 0:
                return RPointPluginResult(plugin_name, False, "")

            # 今日量型（任意即可，但必须存在）
            current_chance = self._daily_chance_cache.get(date_str) or self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            vol_type_str = (getattr(current_chance, "volume_type", None) or "").strip()
            vol_types = [v.strip() for v in vol_type_str.split(",") if v.strip()]
            if not vol_types:
                return RPointPluginResult(plugin_name, False, "")

            # --- 条件1：30交易日累计涨幅 ---
            prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
            # prev_dates[0] = 昨天 ... prev_dates[29] = 往前第30个交易日（含今天共31个交易日）
            if len(prev_dates) < 30:
                return RPointPluginResult(plugin_name, False, "")
            base_date_str = prev_dates[29]
            base_daily = self._daily_cache.get(base_date_str) or self.daily_repo.find_by_date(stock_code, base_date_str)
            if not base_daily or not getattr(base_daily, "close", None):
                return RPointPluginResult(plugin_name, False, "")
            close_base = float(base_daily.close)
            if close_base <= 0:
                return RPointPluginResult(plugin_name, False, "")

            rise_pct = ((close_today - close_base) / close_base) * 100.0
            if rise_pct < 30.0:
                return RPointPluginResult(plugin_name, False, "")

            # --- 条件3：跌破MA20（昨>今<）---
            ma20_list = ma_data.get("ma20") or []
            if current_index >= len(ma20_list) or (current_index - 1) >= len(ma20_list):
                return RPointPluginResult(plugin_name, False, "")
            ma20_today = ma20_list[current_index]
            ma20_yesterday = ma20_list[current_index - 1]
            if ma20_today is None or ma20_yesterday is None:
                return RPointPluginResult(plugin_name, False, "")

            # 昨日收盘（用缓存交易日回推更稳，避免current_index与数据源不一致时的错位）
            yesterday_str = prev_dates[0]
            daily_yesterday = self._daily_cache.get(yesterday_str) or self.daily_repo.find_by_date(stock_code, yesterday_str)
            if not daily_yesterday or not getattr(daily_yesterday, "close", None):
                return RPointPluginResult(plugin_name, False, "")
            close_yesterday = float(daily_yesterday.close)
            if close_yesterday <= 0:
                return RPointPluginResult(plugin_name, False, "")

            if not (close_yesterday > float(ma20_yesterday) and close_today < float(ma20_today)):
                return RPointPluginResult(plugin_name, False, "")

            # --- 条件4：MACD死叉状态 DIF < DEA ---
            dif_list = macd_data.get("dif") or []
            dea_list = macd_data.get("dea") or []
            if current_index >= len(dif_list) or current_index >= len(dea_list):
                return RPointPluginResult(plugin_name, False, "")
            dif_today = dif_list[current_index]
            dea_today = dea_list[current_index]
            if dif_today is None or dea_today is None:
                return RPointPluginResult(plugin_name, False, "")
            if float(dif_today) >= float(dea_today):
                return RPointPluginResult(plugin_name, False, "")

            reason = (
                f"30交易日涨幅{rise_pct:.2f}% (起点{base_date_str}收盘{close_base:.2f}→今日{close_today:.2f})"
                f"+今日量型({vol_type_str})"
                f"+跌破MA20(昨收{close_yesterday:.2f}>MA20{float(ma20_yesterday):.2f}, 今收{close_today:.2f}<MA20{float(ma20_today):.2f})"
                f"+MACD死叉状态(DIF{float(dif_today):.4f}<DEA{float(dea_today):.4f})"
            )
            return RPointPluginResult(plugin_name, True, reason)
        except Exception as e:
            logger.error(f"R点插件-{plugin_name}检查异常: {e}")
            return RPointPluginResult(plugin_name, False, "")

