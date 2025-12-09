"""策略2 - C点评分计算服务"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger
from domain.models.stock import StockGroups

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
                       index: int) -> Tuple[bool, float, str]:
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
        volume_score = self._calculate_volume_score(volume_type, details)
        total_score += volume_score
        
        # 4. K线组合：10分
        kline_score = self._calculate_kline_score(daily_data_30, bullish_pattern, details)
        total_score += kline_score
        
        # 5. 减分：股价偏离10日均线超过20%
        penalty = self._calculate_penalty(ma_data, close_price, index, details)
        total_score += penalty
        
        # 从配置读取触发阈值
        threshold = self.config_service.get_strategy2_threshold()
        
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
        条件：5日 > 10日 > 20日（多头排列）
        """
        score = 0
        
        ma5_current = ma_data['ma5'][index]
        ma10_current = ma_data['ma10'][index]
        ma20_current = ma_data['ma20'][index]
        
        # 判断多头排列：5日 > 10日 > 20日
        bullish_alignment = ma5_current > ma10_current and ma10_current > ma20_current
        
        if bullish_alignment:
            score = 30
            details.append("均线30分(MA5>MA10>MA20)")
        
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
        
        # 2. 金叉（10分）- DIF>DEA，前一日蓝柱，今日红柱（5日内有效）
        bonus_key_golden = f"{stock_code}_macd_golden"
        if self._check_time_window_bonus(stock_code, date, bonus_key_golden, 5):
            score += 10
            macd_details.append("金叉10分")
        else:
            # 前一日蓝柱（MACD<0），今日红柱（MACD>0），且今日DIF>DEA
            golden_cross = (macd_prev < 0 and 
                          macd_current > 0 and 
                          dif_current > dea_current)
            if golden_cross:
                score += 10
                macd_details.append("金叉10分")
                # 记录这个加分，5日内有效
                self._record_bonus(stock_code, bonus_key_golden, date, 5)
        
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
    
    def _calculate_volume_score(self, volume_type: Optional[str], details: List[str]) -> float:
        """
        计算成交量得分：最高30分
        
        异常量（EF）任意一种：0分（优先级最高）
        温和放量（ABCD）任意一种：30分
        其他特殊型（H）：21分（70%权重）
        XY型放量：21分（策略2专用）
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
    
    def clear_cache(self):
        """清空缓存"""
        self._bonus_records.clear()

