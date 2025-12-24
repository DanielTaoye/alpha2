"""策略2 - C点评分计算服务"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger
from domain.models.stock import StockGroups
from domain.services.kline_pattern_service import KLinePatternService

logger = get_logger(__name__)


class Strategy2Service:
    """策略2 - C点评分计算服务（总分≥阈值发C点）"""
    
    def __init__(self):
        from domain.services.config_service import get_config_service
        self.config_service = get_config_service()  # 配置服务
        # 用于记录加分的时间窗口（MA、MACD等）
        self._bonus_records = {}  # {stock_code: {bonus_type: end_date}}
    
    def check_strategy2(self, 
                       stock_code: str, 
                       date: datetime, 
                       close_price: float,
                       ma_data: Dict[str, List[Optional[float]]],
                       macd_data: Dict[str, List[Optional[float]]],
                       volume_type: Optional[str],
                       bullish_pattern: Optional[str],
                       daily_data_30: List[Dict],  # 前30个交易日数据
                       index: int,
                       prev_day_has_r: bool = False,
                       strategy1_reject_by_penalty_plugins: bool = False,
                       stock_nature: Optional[str] = None,
                       prev_has_c: bool = False,
                       penalty_after_strategy2_or_golden: bool = False,
                       penalty_after_r_without_s1c_last3: bool = False,
                       prev_day_deviation_r: bool = False) -> Tuple[bool, float, str]:
        """
        检查策略2是否触发C点
        
        Args:
            stock_code: 股票代码
            date: 当前日期
            close_price: 收盘价
            ma_data: MA数据 {'ma5': [...], 'ma10': [...], 'ma20': [...]}
            macd_data: MACD数据 {'dif': [...], 'dea': [...], 'macd': [...]}
            volume_type: 成交量类型
            bullish_pattern: 多头K线组合
            daily_data_30: 前30个交易日数据（用于判断低位）
            index: 当前K线在数据中的索引
            strategy1_reject_by_penalty_plugins: 策略1被减分插件否决（赔率高胜率低/风险K线/不追涨）
            prev_day_deviation_r: 前一交易日是否为“乖离率偏离”导致的R
            
        Returns:
            (是否触发, 总分, 详细原因)
        """
        total_score = 0
        details = []
        
        # 检查数据完整性
        if not self._check_data_validity(ma_data, macd_data, index):
            return False, 0, "数据不完整"
        
        # 1. 均线总分：30分
        ma_score = self._calculate_ma_score(stock_code, date, ma_data, close_price, index, details)
        total_score += ma_score
        
        # 2. MACD总分：30分
        macd_score = self._calculate_macd_score(stock_code, date, macd_data, index, details)
        total_score += macd_score
        
        # 3. 成交量总分：30分
        volume_score = self._calculate_volume_score(volume_type, details, stock_nature)
        total_score += volume_score

        # 3.5 策略2取消发C 情形1（惩罚项）
        cancel_penalty = self._calculate_cancel_c_penalty(stock_code, daily_data_30, details)
        total_score += cancel_penalty
        
        # 4. K线组合：10分
        kline_score = self._calculate_kline_score(daily_data_30, bullish_pattern, details)
        total_score += kline_score
        
        # 5. 减分：股价偏离10日均线超过20%
        penalty = self._calculate_penalty(ma_data, close_price, index, details)
        total_score += penalty
        
        # 从配置读取触发阈值（支持股性）
        threshold = self.config_service.get_strategy2_threshold(stock_nature)
        
        # 新减分：昨日R由乖离率偏离触发，今日策略2扣43分（全部股性适用）
        if prev_day_deviation_r:
            total_score -= 43
            details.append("昨日R因乖离率偏离，策略2扣43分")
        
        # 情形3：前一日刚发R，且当日原始分数达到阈值，扣45分
        # 先记录未扣前得分用于判断“符合发C条件”
        pre_case3_score = total_score
        if prev_day_has_r and pre_case3_score >= threshold:
            total_score -= 45
            details.append("策略2取消发C情形3扣45分(前一日有R)")
        
        # 情形4：策略2本身达到阈值，且策略1被减分插件（赔率高胜率低/风险K线/不追涨）否决，则再扣55分
        pre_case4_score = total_score
        if strategy1_reject_by_penalty_plugins and pre_case4_score >= threshold:
            total_score -= 55
            details.append("策略2取消发C情形4扣55分(策略1被减分插件否决)")

        # 新逻辑：若前面已有有效C（非R），短线/波段的策略2额外扣38分；中长线不受影响
        if prev_has_c and (stock_nature is None or stock_nature in ["短线", "波段"]):
            total_score -= 38
            details.append("前有C，策略2额外扣38分(仅短线/波段)")

        # 中长线：如果本轮之前（自上次R以来）已出现策略2的C或金色C，则策略2额外扣42分
        if stock_nature == "中长线" and penalty_after_strategy2_or_golden:
            total_score -= 42
            details.append("中长线：已有策略2/金色C，策略2额外扣42分")
        
        # 中长线：近3日内出现过R，且近3日（含当日）无策略1的C，则策略2扣47分
        if stock_nature == "中长线" and penalty_after_r_without_s1c_last3:
            total_score -= 47
            details.append("中长线：近3日有R且无策略1C，策略2扣47分")
        
        # 判断是否触发
        is_triggered = total_score >= threshold
        reason = f"策略2总分: {total_score:.0f}分 ({', '.join(details)})"
        
        if is_triggered:
            logger.info(f"[策略2] {stock_code} {date.strftime('%Y-%m-%d')} 触发C点！阈值{threshold}, {reason}")
        
        return is_triggered, total_score, reason
    
    def _check_data_validity(self, ma_data: Dict, macd_data: Dict, index: int) -> bool:
        """检查数据完整性"""
        if not ma_data or not macd_data:
            return False
        
        # 检查MA数据
        if 'ma5' not in ma_data or 'ma10' not in ma_data or 'ma20' not in ma_data:
            return False
        
        if index >= len(ma_data['ma5']) or index >= len(ma_data['ma10']) or index >= len(ma_data['ma20']):
            return False
        
        if ma_data['ma5'][index] is None or ma_data['ma10'][index] is None or ma_data['ma20'][index] is None:
            return False
        
        # 检查MACD数据
        if 'dif' not in macd_data or 'dea' not in macd_data or 'macd' not in macd_data:
            return False
        
        if index >= len(macd_data['dif']) or index >= len(macd_data['dea']) or index >= len(macd_data['macd']):
            return False
        
        if macd_data['dif'][index] is None or macd_data['dea'][index] is None:
            return False
        
        return True
    
    def _calculate_ma_score(self, stock_code: str, date: datetime, ma_data: Dict, 
                           close_price: float, index: int, details: List[str]) -> float:
        """
        计算均线得分：30分
        条件：
        - 5日 > 10日 > 20日（30分）
        - 5日 > 20日 > 10日 且 今日MA5>昨日MA5（20分）
        """
        score = 0
        
        ma5_current = ma_data['ma5'][index]
        ma10_current = ma_data['ma10'][index]
        ma20_current = ma_data['ma20'][index]
        ma5_prev = ma_data['ma5'][index - 1] if index >= 1 else None
        
        # 判断多头排列：5日 > 10日 > 20日
        bullish_alignment = ma5_current > ma10_current and ma10_current > ma20_current
        
        if bullish_alignment:
            score = 30
            details.append("均线30分(MA5>MA10>MA20)")
        else:
            # 次优排列：5日 > 20日 > 10日
            alt_alignment = ma5_current > ma20_current and ma20_current > ma10_current
            ma5_rising = ma5_prev is not None and ma5_current > ma5_prev
            if alt_alignment and ma5_rising:
                score = 20
                details.append("均线20分(MA5>MA20>MA10)")
        
        return score
    
    def _calculate_macd_score(self, stock_code: str, date: datetime, macd_data: Dict, 
                             index: int, details: List[str]) -> float:
        """
        计算MACD得分：最高35分
        
        评分项：
        1. DIF拐头向上（10分）- 往前数10根K线，当日和前一日DIF均大于前8个交易日（5日内有效）
        2. 金叉（10分）- DIF>DEA，前一日蓝柱，今日红柱（5日内有效）
        3. 多头排列1（10分）- DIF≥DEA>0 且 MACD>0
        4. 多头排列2（5分）- 0>DIF≥DEA 且 MACD>0
        """
        score = 0
        macd_details = []
        
        dif_current = macd_data['dif'][index]
        dea_current = macd_data['dea'][index]
        macd_current = macd_data['macd'][index]
        
        # 需要前一日数据
        if index < 1:
            return score
        
        dif_prev = macd_data['dif'][index - 1]
        dea_prev = macd_data['dea'][index - 1]
        macd_prev = macd_data['macd'][index - 1]
        
        if dif_prev is None or dea_prev is None or macd_prev is None:
            return score
        
        # 1. DIF拐头向上（10分）- 当日和前一日DIF均大于前8个交易日（5日内有效）
        bonus_key_turn = f"{stock_code}_dif_turn_up"
        if self._check_time_window_bonus(stock_code, date, bonus_key_turn, 5):
            score += 10
            macd_details.append("DIF拐头10分")
        elif index >= 10:
            # 往前数10根K线，取前8个交易日的DIF
            dif_list = [macd_data['dif'][i] for i in range(index - 9, index - 1) 
                       if macd_data['dif'][i] is not None]
            if len(dif_list) == 8:
                max_prev_8 = max(dif_list)
                # 当日和前一日DIF均大于前8个交易日
                if dif_current > max_prev_8 and dif_prev > max_prev_8:
                    score += 10
                    macd_details.append("DIF拐头10分")
                    # 记录这个加分，5日内有效
                    self._record_bonus(stock_code, bonus_key_turn, date, 5)
        
        # 2. 金叉（10分）- 近5个交易日内出现：前一日蓝柱（MACD<0），当日红柱（MACD>0），且当日DIF>DEA
        if self._has_recent_golden_cross(macd_data, index, lookback=5):
            score += 10
            macd_details.append("金叉10分(近5日)")
        
        # 3. 多头排列1（10分）- DIF≥DEA>0 且 MACD>0
        bullish_alignment_1 = (dif_current >= dea_current and 
                               dea_current > 0 and 
                               macd_current > 0)
        if bullish_alignment_1:
            score += 10
            macd_details.append("多头排列1(10分)")
        
        # 4. 多头排列2（5分）- 0>DIF≥DEA 且 MACD>0
        bullish_alignment_2 = (0 > dif_current and 
                               dif_current >= dea_current and 
                               macd_current > 0)
        if bullish_alignment_2:
            score += 5
            macd_details.append("多头排列2(5分)")
        
        if macd_details:
            details.append(f"MACD{score}分({'+'.join(macd_details)})")
        
        return score
    
    def _calculate_volume_score(self, volume_type: Optional[str], details: List[str],
                               stock_nature: Optional[str] = None) -> float:
        """
        计算成交量得分：最高30分
        
        异常量（EF）任意一种：0分（优先级最高）
        温和放量（ABCD）任意一种：30分
        其他特殊型（H）：21分（70%权重）
        XY型放量：21分（策略2专用）
        中长线 + S型额外加分：+10
        """
        score = 0
        
        if not volume_type:
            return score
        
        volume_types = [vt.strip() for vt in volume_type.split(',')]
        
        # 异常量（E或F）优先级最高，如果包含E或F，则得0分
        if 'E' in volume_types or 'F' in volume_types:
            return 0
        
        # 温和放量（ABCD）
        moderate_volume = any(vt in ['A', 'B', 'C', 'D'] for vt in volume_types)
        
        # 特殊型（H）
        special_volume = 'H' in volume_types
        
        # XY型放量（策略2专用）
        xy_volume = 'X' in volume_types or 'Y' in volume_types
        
        if moderate_volume:
            score = 30
            details.append("成交量30分(温和放量)")
        elif special_volume or xy_volume:
            score = 21
            if special_volume and xy_volume:
                details.append("成交量21分(H/XY型放量)")
            elif special_volume:
                details.append("成交量21分(H型放量)")
            else:
                details.append("成交量21分(XY型放量)")
        
        # 中长线 + S型成交量加10分（在原有分数基础上累加）
        if 'S' in volume_types:
            normalized_nature = stock_nature
            if normalized_nature in ["长线", "中长", "中长线"]:
                score += 10
                details.append("中长线S型成交量+10分")
        
        return score
    
    def _calculate_kline_score(self, daily_data_30: List[Dict], bullish_pattern: Optional[str], 
                               details: List[str]) -> float:
        """
        计算K线组合得分：10分
        
        条件：低位 + 出现任意多头K线组合
        低位定义：前30个交易日区间振幅>20%，当前股价处于10%水位区间
        """
        score = 0
        
        if not daily_data_30 or len(daily_data_30) < 30:
            return score
        
        if not bullish_pattern:
            return score
        
        # 判断是否处于低位
        is_low_position = self._check_low_position(daily_data_30)
        
        if is_low_position:
            score = 10
            details.append(f"K线组合10分(低位+{bullish_pattern})")
        
        return score
    
    def _check_low_position(self, daily_data_30: List[Dict]) -> bool:
        """
        判断是否处于低位
        
        条件：前30个交易日区间振幅>20%，当前股价处于10%水位区间
        """
        if len(daily_data_30) < 30:
            return False
        
        # 获取前30日的最高价和最低价
        highs = [float(d['high']) for d in daily_data_30 if 'high' in d]
        lows = [float(d['low']) for d in daily_data_30 if 'low' in d]
        
        if not highs or not lows:
            return False
        
        max_high = max(highs)
        min_low = min(lows)
        
        # 区间振幅
        amplitude = (max_high - min_low) / min_low if min_low > 0 else 0
        
        if amplitude <= 0.20:  # 振幅需要>20%
            return False
        
        # 当前价格（最后一天的收盘价）
        current_price = float(daily_data_30[-1].get('close', 0))
        
        # 10%水位区间：最低价 到 (最低价 + 振幅*10%)
        water_level_10 = min_low + (max_high - min_low) * 0.10
        
        # 当前价格在10%水位区间内
        is_low = min_low <= current_price <= water_level_10
        
        return is_low
    
    def _calculate_penalty(self, ma_data: Dict, close_price: float, index: int, 
                          details: List[str]) -> float:
        """
        计算减分：股价偏离10日均线超过20%，减50分
        """
        penalty = 0
        
        ma10_current = ma_data['ma10'][index]
        
        if ma10_current is None or ma10_current == 0:
            return penalty
        
        # 计算偏离度
        deviation = abs(close_price - ma10_current) / ma10_current
        
        if deviation > 0.20:
            penalty = -50
            details.append(f"偏离MA10超20%扣50分(偏离{deviation*100:.1f}%)")
        
        return penalty

    def _calculate_cancel_c_penalty(self, stock_code: str, daily_data_30: List[Dict],
                                    details: List[str]) -> float:
        """
        策略2取消发C 情形1：
        - 当日跌幅≥2%的阴线，扣42分
        - 若跌幅<2%但属于下列K线，同样扣42分：
            高开低走、冲高回落阳线、冲高回落阴线、冲高回落阴十字星、冲高回落阳十字星
        - 或当日为阴线 且 3A>C 且 3B>C
        - 或当日为阴线 且 3B>A 且 3B>C
        """
        if not daily_data_30:
            return 0
        
        today = daily_data_30[-1]
        open_p = today.get('open')
        high_p = today.get('high')
        low_p = today.get('low')
        close_p = today.get('close')
        prev_close = today.get('prev_close')
        
        if None in (open_p, high_p, low_p, close_p) or open_p is None:
            return 0
        
        is_bearish = close_p < open_p
        # 跌幅相对开盘价
        decline_pct_open = (close_p - open_p) / open_p * 100 if open_p else None
        
        penalty = 0
        reason = ""
        
        # 条件1：阴线且跌幅≥2%（相对开盘）
        if is_bearish and decline_pct_open is not None and decline_pct_open <= -2:
            penalty = -42
            reason = f"阴线跌幅{decline_pct_open:.2f}%相对开盘"
        
        # 计算ABC
        abc = KLinePatternService.calculate_abc(open_p, close_p, high_p, low_p)
        
        # 条件2：跌幅<2% 且 满足以下任一
        # - 特定K线形态（高开低走、冲高回落阳/阴线、冲高回落阴/阳十字星）
        # - 阴线且 3A>C 且 3B>C
        # - 阴线且 3B>A 且 3B>C
        if decline_pct_open is not None and decline_pct_open > -2:
            pattern = KLinePatternService.identify_pattern(stock_code, open_p, close_p, high_p, low_p, prev_close)
            risky_patterns = ["高开低走", "冲高回落阳线", "冲高回落阴线", "冲高回落阴十字星", "冲高回落阳十字星"]
            
            trigger = False
            local_reason = ""
            
            if pattern in risky_patterns:
                trigger = True
                local_reason = pattern
            elif is_bearish and (3 * abc.a > abc.c) and (3 * abc.b > abc.c):
                trigger = True
                local_reason = "3A>C且3B>C"
            elif is_bearish and (3 * abc.b > abc.a) and (3 * abc.b > abc.c):
                trigger = True
                local_reason = "3B>A且3B>C"
            
            if trigger:
                penalty = -42
                reason = f"{local_reason}, 跌幅{decline_pct_open:.2f}%相对开盘"
        
        # 条件3（情形2）：前5日涨幅过大（起止收盘比，需6根收盘价确保间隔5日）
        if len(daily_data_30) >= 6:
            window = daily_data_30[-6:]
            first_close = window[0].get('close')
            last_close = window[-1].get('close')
            all_bullish_5 = all(d.get('close') is not None and d.get('open') is not None and d['close'] > d['open'] for d in window[1:])
            
            if first_close and first_close > 0 and last_close:
                cum5 = (last_close - first_close) / first_close * 100
                is_main = KLinePatternService.is_main_board(stock_code)
                thresh_bull = 35 if is_main else 50  # 连阳且累涨阈值
                thresh_cum = 25 if is_main else 35   # 纯累涨阈值
                
                triggered_case2 = False
                case2_reason = ""
                
                if all_bullish_5 and cum5 >= thresh_bull:
                    triggered_case2 = True
                    case2_reason = f"前5日连阳累涨{cum5:.2f}%≥{thresh_bull}%"
                elif cum5 > thresh_cum:
                    triggered_case2 = True
                    case2_reason = f"前5日累涨{cum5:.2f}%>{thresh_cum}%"
                
                if triggered_case2:
                    penalty = min(penalty, -50) if penalty else -50
                    if reason:
                        reason = reason + "; " + case2_reason
                    else:
                        reason = case2_reason
        
        if penalty != 0:
            details.append(f"策略2取消发C情形扣分{abs(penalty)}分({reason})")
        
        return penalty
    
    def _check_time_window_bonus(self, stock_code: str, date: datetime, bonus_key: str, 
                                 window_days: int) -> bool:
        """检查时间窗口内的加分是否有效"""
        if stock_code not in self._bonus_records:
            return False
        
        if bonus_key not in self._bonus_records[stock_code]:
            return False
        
        end_date = self._bonus_records[stock_code][bonus_key]
        return date <= end_date
    
    def _record_bonus(self, stock_code: str, bonus_key: str, trigger_date: datetime, 
                     window_days: int):
        """记录加分，设置有效期"""
        if stock_code not in self._bonus_records:
            self._bonus_records[stock_code] = {}
        
        end_date = trigger_date + timedelta(days=window_days)
        self._bonus_records[stock_code][bonus_key] = end_date
        logger.debug(f"记录加分: {bonus_key}, 有效期至 {end_date.strftime('%Y-%m-%d')}")
    
    def _has_recent_golden_cross(self, macd_data: Dict, index: int, lookback: int = 5) -> bool:
        """
        检查近N个交易日内是否出现金叉：
        条件（保持原判定语义）：
        - 前一日MACD<0（蓝柱）
        - 当日MACD>0（红柱）
        - 当日DIF>DEA
        """
        start = max(1, index - lookback + 1)
        for i in range(start, index + 1):
            macd_prev = macd_data['macd'][i - 1]
            macd_curr = macd_data['macd'][i]
            dif_curr = macd_data['dif'][i]
            dea_curr = macd_data['dea'][i]
            
            if macd_prev is None or macd_curr is None or dif_curr is None or dea_curr is None:
                continue
            
            golden = (macd_prev < 0 and macd_curr > 0 and dif_curr > dea_curr)
            if golden:
                return True
        return False
    
    def clear_cache(self):
        """清空缓存"""
        self._bonus_records.clear()

