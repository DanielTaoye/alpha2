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
        # 用于记录MACD加分的时间窗口
        self._macd_bonus_records = {}  # {stock_code: {bonus_type: end_date}}
    
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
        ma_score = self._calculate_ma_score(ma_data, close_price, index, details)
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
    
    def _calculate_ma_score(self, ma_data: Dict, close_price: float, index: int, details: List[str]) -> float:
        """
        计算均线得分：30分
        条件：5日线上穿10日线 且 K线当前价格 > 20日均线价格
        """
        score = 0
        
        ma5_current = ma_data['ma5'][index]
        ma10_current = ma_data['ma10'][index]
        ma20_current = ma_data['ma20'][index]
        
        # 检查是否有前一日数据
        if index < 1:
            return score
        
        ma5_prev = ma_data['ma5'][index - 1]
        ma10_prev = ma_data['ma10'][index - 1]
        
        if ma5_prev is None or ma10_prev is None:
            return score
        
        # 判断5日线上穿10日线
        golden_cross = ma5_prev <= ma10_prev and ma5_current > ma10_current
        
        # 判断当前价格 > 20日均线
        price_above_ma20 = close_price > ma20_current
        
        if golden_cross and price_above_ma20:
            score = 30
            details.append("均线30分(MA5金叉MA10+价格>MA20)")
        
        return score
    
    def _calculate_macd_score(self, stock_code: str, date: datetime, macd_data: Dict, 
                             index: int, details: List[str]) -> float:
        """
        计算MACD得分：最高30分
        
        评分项：
        1. DIF拐头向上（10分）
        2. 金叉（10分）- DIF上穿DEA
        3. 多头排列（10分）- DIF > DEA > 0 且 MACD > 0
        4. 强势多头（5分）- 当日和前一日DIF > 前8日所有DIF（5日内有效）
        5. 柱状图反转（5分）- 前日蓝柱今日红柱（5日内有效）
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
        
        # 1. DIF拐头向上（10分）
        # 需要前2日数据判断拐头
        if index >= 2:
            dif_prev2 = macd_data['dif'][index - 2]
            if dif_prev2 is not None:
                # 拐头：前天>昨天 且 昨天<今天
                if dif_prev2 > dif_prev and dif_prev < dif_current:
                    score += 10
                    macd_details.append("DIF拐头10分")
        
        # 2. 金叉（10分）- DIF上穿DEA
        golden_cross = dif_prev <= dea_prev and dif_current > dea_current
        if golden_cross:
            score += 10
            macd_details.append("MACD金叉10分")
        
        # 3. 多头排列（10分）- DIF > DEA > 0 且 MACD > 0
        bullish_alignment = dif_current > dea_current and dea_current > 0 and macd_current > 0
        if bullish_alignment:
            score += 10
            macd_details.append("多头排列10分")
        
        # 4. 强势多头（5分）- 当日和前一日DIF > 前8日所有DIF（5日内有效）
        bonus_key = f"{stock_code}_strong_bull"
        if self._check_time_window_bonus(stock_code, date, bonus_key, 5):
            score += 5
            macd_details.append("强势多头5分")
        elif index >= 10:
            # 检查是否触发新的强势多头
            dif_list = [macd_data['dif'][i] for i in range(index - 9, index - 1) if macd_data['dif'][i] is not None]
            if len(dif_list) == 8:
                max_prev_8 = max(dif_list)
                if dif_current > max_prev_8 and dif_prev > max_prev_8:
                    score += 5
                    macd_details.append("强势多头5分")
                    # 记录这个加分，5日内有效
                    self._record_bonus(stock_code, bonus_key, date, 5)
        
        # 5. 柱状图反转（5分）- 前日蓝柱今日红柱（5日内有效）
        bonus_key2 = f"{stock_code}_bar_reverse"
        if self._check_time_window_bonus(stock_code, date, bonus_key2, 5):
            score += 5
            macd_details.append("柱反转5分")
        else:
            # 检查是否触发新的反转
            # 前日蓝柱（MACD<0）今日红柱（MACD>0）且DIF>DEA
            bar_reverse = macd_prev < 0 and macd_current > 0 and dif_current > dea_current
            if bar_reverse:
                score += 5
                macd_details.append("柱反转5分")
                # 记录这个加分，5日内有效
                self._record_bonus(stock_code, bonus_key2, date, 5)
        
        if macd_details:
            details.append(f"MACD{score}分({'+'.join(macd_details)})")
        
        return score
    
    def _calculate_volume_score(self, volume_type: Optional[str], details: List[str]) -> float:
        """
        计算成交量得分：最高30分
        
        异常量（EF）任意一种：0分（优先级最高）
        温和放量（ABCD）任意一种：30分
        其他特殊型（H）：21分（70%权重）
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
        
        if moderate_volume:
            score = 30
            details.append("成交量30分(温和放量)")
        elif special_volume:
            score = 21
            details.append("成交量21分(H型放量)")
        
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
        if stock_code not in self._macd_bonus_records:
            return False
        
        if bonus_key not in self._macd_bonus_records[stock_code]:
            return False
        
        end_date = self._macd_bonus_records[stock_code][bonus_key]
        return date <= end_date
    
    def _record_bonus(self, stock_code: str, bonus_key: str, trigger_date: datetime, 
                     window_days: int):
        """记录加分，设置有效期"""
        if stock_code not in self._macd_bonus_records:
            self._macd_bonus_records[stock_code] = {}
        
        end_date = trigger_date + timedelta(days=window_days)
        self._macd_bonus_records[stock_code][bonus_key] = end_date
        logger.debug(f"记录加分: {bonus_key}, 有效期至 {end_date.strftime('%Y-%m-%d')}")
    
    def clear_cache(self):
        """清空缓存"""
        self._macd_bonus_records.clear()

