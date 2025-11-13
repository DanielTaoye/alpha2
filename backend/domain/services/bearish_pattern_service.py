"""空头组合识别服务"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from domain.services.kline_pattern_service import KLinePatternService
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from domain.services.period_service import PeriodService
import pymysql.cursors

logger = get_logger(__name__)


class BearishPatternService:
    """空头组合识别服务"""
    
    @staticmethod
    def identify_bearish_patterns(
        stock_code: str,
        table_name: str,
        target_date: datetime
    ) -> List[str]:
        """
        识别指定日期的空头组合
        
        Args:
            stock_code: 股票代码
            table_name: 股票表名
            target_date: 目标日期
            
        Returns:
            匹配的空头组合列表，如 ["十字星+中阴", "冲高回落阴线+阴线"]
        """
        try:
            # 获取足够的历史数据（需要前5天的数据）
            start_date = target_date - timedelta(days=10)
            
            daily_data = BearishPatternService._get_daily_data(
                table_name, start_date, target_date
            )
            
            if not daily_data or len(daily_data) < 2:
                return []
            
            # 按日期排序（从旧到新）
            daily_data.sort(key=lambda x: x['date'])
            
            # 找到目标日期的索引
            target_idx = None
            target_date_only = target_date.date() if isinstance(target_date, datetime) else target_date
            
            for i, data in enumerate(daily_data):
                data_date = data['date']
                # 统一处理日期类型
                if isinstance(data_date, datetime):
                    data_date_only_check = data_date.date()
                elif isinstance(data_date, type(target_date_only)):
                    data_date_only_check = data_date
                else:
                    continue
                
                if data_date_only_check == target_date_only:
                    target_idx = i
                    break
            
            if target_idx is None or target_idx < 1:
                return []
            
            matched_patterns = []
            
            # 获取目标日期的数据
            today = daily_data[target_idx]
            prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None
            
            # 1. 十字星+中阴
            pattern1 = BearishPatternService._check_pattern1(
                stock_code, prev_day, today
            )
            if pattern1:
                matched_patterns.append(pattern1)
            
            # 2. 冲高回落阴线+阴线
            pattern2 = BearishPatternService._check_pattern2(
                stock_code, prev_day, today
            )
            if pattern2:
                matched_patterns.append(pattern2)
            
            # 3. 带上影线的阴线/阳线+阴线
            pattern3 = BearishPatternService._check_pattern3(
                stock_code, prev_day, today
            )
            if pattern3:
                matched_patterns.append(pattern3)
            
            # 4. 带上影阳线+十字星+（阴线或带上影线阴线）
            pattern4 = BearishPatternService._check_pattern4(
                stock_code, daily_data, target_idx
            )
            if pattern4:
                matched_patterns.append(pattern4)
            
            # 5. 双针探顶
            pattern5 = BearishPatternService._check_pattern5(
                stock_code, daily_data, target_idx
            )
            if pattern5:
                matched_patterns.append(pattern5)
            
            # 6. 触底反弹阳线+吞没阴线
            pattern6 = BearishPatternService._check_pattern6(
                stock_code, prev_day, today
            )
            if pattern6:
                matched_patterns.append(pattern6)
            
            # 7. 阴包阳
            pattern7 = BearishPatternService._check_pattern7(
                stock_code, prev_day, today
            )
            if pattern7:
                matched_patterns.append(pattern7)
            
            # 8. T字板/一字板+带上影阴线/高开回落阴线
            pattern8 = BearishPatternService._check_pattern8(
                stock_code, prev_day, today
            )
            if pattern8:
                matched_patterns.append(pattern8)
            
            # 9. 乌云盖顶
            pattern9 = BearishPatternService._check_pattern9(
                stock_code, prev_day, today
            )
            if pattern9:
                matched_patterns.append(pattern9)
            
            # 10. 触底反弹十字星+吞没阴线
            pattern10 = BearishPatternService._check_pattern10(
                stock_code, prev_day, today
            )
            if pattern10:
                matched_patterns.append(pattern10)
            
            # 11. 放量冲高回落阴线+次日未反包
            pattern11 = BearishPatternService._check_pattern11(
                stock_code, prev_day, today
            )
            if pattern11:
                matched_patterns.append(pattern11)
            
            # 12. 一阴穿三阳
            pattern12 = BearishPatternService._check_pattern12(
                stock_code, daily_data, target_idx
            )
            if pattern12:
                matched_patterns.append(pattern12)
            
            # 13. 吞没阴线（二阴或三阴）吞一根阳线
            pattern13 = BearishPatternService._check_pattern13(
                stock_code, daily_data, target_idx
            )
            if pattern13:
                matched_patterns.append(pattern13)
            
            # 14. 吞没阴线（1-3根最终吞没一根阳线）
            pattern14 = BearishPatternService._check_pattern14(
                stock_code, daily_data, target_idx
            )
            if pattern14:
                matched_patterns.append(pattern14)
            
            return matched_patterns
            
        except Exception as e:
            logger.error(f"识别空头组合失败: {stock_code} {target_date}: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _check_pattern1(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """1. 十字星+中阴"""
        if not prev_day:
            return None
        
        # 前一日为十字星
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern != "十字星":
            return None
        
        # 当日出现跌幅3%/5%的阴线（主板3% 创业科创5%）
        is_main = KLinePatternService.is_main_board(stock_code)
        decline_threshold = 3.0 if is_main else 5.0
        
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        # 计算跌幅
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct >= decline_threshold:
            return "十字星+中阴"
        
        return None
    
    @staticmethod
    def _check_pattern2(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """2. 冲高回落阴线+阴线"""
        if not prev_day:
            return None
        
        # 前一日为振幅大于5%的冲高回落阴线
        prev_amplitude = BearishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern != "冲高回落阴线" or prev_amplitude <= 5.0:
            return None
        
        # 当日为跌幅大于3%的阴线
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct > 3.0:
            return "冲高回落阴线+阴线"
        
        return None
    
    @staticmethod
    def _check_pattern3(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """3. 带上影线的阴线/阳线+阴线"""
        if not prev_day:
            return None
        
        # 前一日为振幅大于5%的带上影的（阴线或阳线）
        prev_amplitude = BearishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        # 检查是否为带上影线的K线
        valid_patterns = [
            "冲高回落阳线", "冲高回落阴线",
            "冲高回落阳十字星", "冲高回落阴十字星"
        ]
        
        if prev_pattern not in valid_patterns or prev_amplitude <= 5.0:
            return None
        
        # 当日为跌幅大于3%的阴线
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct > 3.0:
            return "带上影线的阴线/阳线+阴线"
        
        return None
    
    @staticmethod
    def _check_pattern4(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """4. 带上影阳线+十字星+（阴线或带上影线阴线）"""
        if target_idx < 2:
            return None
        
        # 往前数2根K线
        day_before_2 = daily_data[target_idx - 2]  # 第一根K线
        day_before_1 = daily_data[target_idx - 1]  # 第二根K线（十字星）
        today = daily_data[target_idx]  # 当日
        
        # 第一根为振幅大于5%的带上影的阳线
        amplitude_2 = BearishPatternService._calculate_amplitude(
            day_before_2['high'], day_before_2['low'],
            daily_data[target_idx - 3]['close'] if target_idx >= 3 else day_before_2['close']
        )
        pattern_2 = KLinePatternService.identify_pattern(
            stock_code, day_before_2['open'], day_before_2['close'],
            day_before_2['high'], day_before_2['low']
        )
        
        valid_patterns_2 = ["冲高回落阳线", "冲高回落阳十字星"]
        if pattern_2 not in valid_patterns_2 or amplitude_2 <= 5.0:
            return None
        
        # 第二根K线为十字星
        pattern_1 = KLinePatternService.identify_pattern(
            stock_code, day_before_1['open'], day_before_1['close'],
            day_before_1['high'], day_before_1['low']
        )
        if pattern_1 != "十字星":
            return None
        
        # 当日出现以下K线任意一种
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        today_amplitude = BearishPatternService._calculate_amplitude(
            today['high'], today['low'], day_before_1['close']
        )
        
        # 跌幅>3%的阴线
        is_today_negative = today['close'] < today['open']
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        # 检查是否符合条件
        if (is_today_negative and decline_pct > 3.0) or \
           (today_pattern == "冲高回落阴线" and today_amplitude > 5.0) or \
           (today_pattern == "冲高回落阴十字星" and today_amplitude > 5.0) or \
           (today_pattern == "冲高回落阳线" and today_amplitude > 5.0):
            return "带上影阳线+十字星+（阴线或带上影线阴线）"
        
        return None
    
    @staticmethod
    def _check_pattern5(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """5. 双针探顶"""
        if target_idx < 1:
            return None
        
        # 前一天或前两天出现振幅>6%以上的带上影线的K线
        prev_patterns = []
        prev_highs = []
        
        for i in range(max(0, target_idx - 2), target_idx):
            day = daily_data[i]
            amplitude = BearishPatternService._calculate_amplitude(
                day['high'], day['low'],
                daily_data[i-1]['close'] if i > 0 else day['close']
            )
            pattern = KLinePatternService.identify_pattern(
                stock_code, day['open'], day['close'], day['high'], day['low']
            )
            
            if amplitude > 6.0 and pattern in ["冲高回落阳线", "冲高回落阴线", "十字星",
                                                "冲高回落阳十字星", "冲高回落阴十字星"]:
                prev_patterns.append(pattern)
                prev_highs.append(day['high'])
        
        if not prev_patterns:
            return None
        
        # 当日再次出现带上影线的K线
        today = daily_data[target_idx]
        today_amplitude = BearishPatternService._calculate_amplitude(
            today['high'], today['low'], daily_data[target_idx - 1]['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if today_amplitude <= 6.0:
            return None
        
        if today_pattern not in ["冲高回落阳线", "冲高回落阴线", "十字星",
                                 "冲高回落阳十字星", "冲高回落阴十字星"]:
            return None
        
        # 且两者最高价价格相差<1.5%
        today_high = today['high']
        for prev_high in prev_highs:
            if prev_high > 0:
                price_diff_pct = abs(today_high - prev_high) / prev_high * 100
                if price_diff_pct < 1.5:
                    return "双针探顶"
        
        return None
    
    @staticmethod
    def _check_pattern6(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """6. 触底反弹阳线+吞没阴线"""
        if not prev_day:
            return None
        
        # 前一日为振幅>5%的触底反弹阳线
        prev_amplitude = BearishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern != "触底反弹阳线" or prev_amplitude <= 5.0:
            return None
        
        # 当日为阴线，且当日收盘价≤前一日最低价
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        if today['close'] <= prev_day['low']:
            return "触底反弹阳线+吞没阴线"
        
        return None
    
    @staticmethod
    def _check_pattern7(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """7. 阴包阳"""
        if not prev_day:
            return None
        
        # 前一天为大于5%以上，B>3%/5%（主板3%，创业科创5%）的阳线
        prev_abc = KLinePatternService.calculate_abc(
            prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        prev_change = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
        prev_change_pct = prev_change * 100
        
        is_prev_positive = prev_day['close'] > prev_day['open']
        if not is_prev_positive:
            return None
        
        is_main = KLinePatternService.is_main_board(stock_code)
        b_threshold = 3.0 if is_main else 5.0
        prev_b_ratio = (prev_abc.b / prev_day['low']) * 100 if prev_day['low'] > 0 else 0
        
        if prev_change_pct <= 5.0 or prev_b_ratio <= b_threshold:
            return None
        
        # 后一天为阴线，且当日收盘价<前一天开盘价
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        if today['close'] < prev_day['open']:
            return "阴包阳"
        
        return None
    
    @staticmethod
    def _check_pattern8(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """8. T字板/一字板+带上影阴线/高开回落阴线"""
        if not prev_day:
            return None
        
        # 前一日为T字型或一字型K线
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern not in ["T字型涨停", "一字涨停", "T字型跌停", "一字跌停"]:
            return None
        
        # 当日出现振幅超5%以上，带上影的阴线
        today_amplitude = BearishPatternService._calculate_amplitude(
            today['high'], today['low'], prev_day['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if today_amplitude <= 5.0:
            return None
        
        valid_today_patterns = [
            "冲高回落阴线", "冲高回落阴十字星",
            "高开低走"
        ]
        
        # 检查是否为带上影的阴线
        if today_pattern in valid_today_patterns:
            return "T字板/一字板+带上影阴线/高开回落阴线"
        
        # 或者检查是否为高开回落阴线（开盘价>前一日收盘价，收盘价<开盘价）
        if today['open'] > prev_day['close'] and today['close'] < today['open']:
            return "T字板/一字板+带上影阴线/高开回落阴线"
        
        return None
    
    @staticmethod
    def _check_pattern9(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """9. 乌云盖顶"""
        if not prev_day:
            return None
        
        # 当日为大中阴，跌幅大于5%以上
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct <= 5.0:
            return None
        
        # 且当日最高价>前一日收盘价
        if today['high'] > prev_day['close']:
            return "乌云盖顶"
        
        return None
    
    @staticmethod
    def _check_pattern10(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """10. 触底反弹十字星+吞没阴线"""
        if not prev_day:
            return None
        
        # 前一日为触底反弹阴十字星或阳十字星
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern not in ["触底反弹十字星"]:
            return None
        
        # 当日出现跌幅大于5%的阴线
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        decline = (today['close'] - today['open']) / today['open'] if today['open'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct > 5.0:
            return "触底反弹十字星+吞没阴线"
        
        return None
    
    @staticmethod
    def _check_pattern11(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """11. 放量冲高回落阴线+次日未反包"""
        if not prev_day:
            return None
        
        # 前一日为振幅大于5%且跌幅大于4.5%的阴线，或振幅大于10%且跌幅大于2%的阴线
        prev_amplitude = BearishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        if prev_pattern != "冲高回落阴线":
            return None
        
        prev_decline = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
        prev_decline_pct = abs(prev_decline) * 100
        
        # 检查条件：(振幅>5%且跌幅>4.5%) 或 (振幅>10%且跌幅>2%)
        condition1 = prev_amplitude > 5.0 and prev_decline_pct > 4.5
        condition2 = prev_amplitude > 10.0 and prev_decline_pct > 2.0
        
        if not (condition1 or condition2):
            return None
        
        # 次日收盘价仍小于前一日收盘价
        if today['close'] < prev_day['close']:
            return "放量冲高回落阴线+次日未反包"
        
        return None
    
    @staticmethod
    def _check_pattern12(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """12. 一阴穿三阳"""
        if target_idx < 3:
            return None
        
        # 当日为大阴线
        today = daily_data[target_idx]
        is_today_negative = today['close'] < today['open']
        if not is_today_negative:
            return None
        
        # 该阴线前三日连续收涨（每日的收盘价均大于前一日收盘价）
        consecutive_positive_days = 0
        first_positive_idx = None
        
        for i in range(target_idx - 1, max(0, target_idx - 4), -1):
            if i < 0:
                break
            day = daily_data[i]
            prev_day = daily_data[i - 1] if i > 0 else None
            
            if prev_day and day['close'] > prev_day['close']:
                if first_positive_idx is None:
                    first_positive_idx = i
                consecutive_positive_days += 1
            else:
                break
        
        if consecutive_positive_days < 3:
            return None
        
        # 该阴线的收盘价<首个阳线的最低价
        if first_positive_idx is not None:
            first_positive_low = daily_data[first_positive_idx]['low']
            if today['close'] < first_positive_low:
                return "一阴穿三阳"
        
        return None
    
    @staticmethod
    def _check_pattern13(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """13. 吞没阴线（二阴或三阴）吞一根阳线"""
        if target_idx < 2:
            return None
        
        # 往前找B>3%且涨幅>5%的阳线
        start_positive_idx = None
        for i in range(target_idx - 1, max(0, target_idx - 4), -1):
            if i < 0:
                break
            day = daily_data[i]
            is_positive = day['close'] > day['open']
            if not is_positive:
                continue
            
            abc = KLinePatternService.calculate_abc(
                day['open'], day['close'], day['high'], day['low']
            )
            b_ratio = (abc.b / day['low']) * 100 if day['low'] > 0 else 0
            change = (day['close'] - day['open']) / day['open'] if day['open'] > 0 else 0
            change_pct = change * 100
            
            if b_ratio > 3.0 and change_pct > 5.0:
                start_positive_idx = i
                break
        
        if start_positive_idx is None:
            return None
        
        # 之后1-3根阴线跌穿起始阳线的开盘价
        start_positive_open = daily_data[start_positive_idx]['open']
        negative_count = 0
        
        for i in range(start_positive_idx + 1, target_idx + 1):
            if i >= len(daily_data):
                break
            day = daily_data[i]
            is_negative = day['close'] < day['open']
            if is_negative:
                negative_count += 1
                if day['close'] < start_positive_open:
                    if 1 <= negative_count <= 3:
                        return "吞没阴线（二阴或三阴）吞一根阳线"
        
        return None
    
    @staticmethod
    def _check_pattern14(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """14. 吞没阴线（1-3根最终吞没一根阳线）"""
        if target_idx < 1:
            return None
        
        # 往前找B>3%且涨幅>5%的阳线
        start_positive_idx = None
        for i in range(target_idx - 1, max(0, target_idx - 4), -1):
            if i < 0:
                break
            day = daily_data[i]
            is_positive = day['close'] > day['open']
            if not is_positive:
                continue
            
            abc = KLinePatternService.calculate_abc(
                day['open'], day['close'], day['high'], day['low']
            )
            b_ratio = (abc.b / day['low']) * 100 if day['low'] > 0 else 0
            change = (day['close'] - day['open']) / day['open'] if day['open'] > 0 else 0
            change_pct = change * 100
            
            if b_ratio > 3.0 and change_pct > 5.0:
                start_positive_idx = i
                break
        
        if start_positive_idx is None:
            return None
        
        # 之后1-3天（截止当前）跌穿起始阳线的开盘价
        start_positive_open = daily_data[start_positive_idx]['open']
        days_since_positive = target_idx - start_positive_idx
        
        if 1 <= days_since_positive <= 3:
            # 检查当前日是否为阴线且收盘价<起始阳线开盘价
            today = daily_data[target_idx]
            is_today_negative = today['close'] < today['open']
            if is_today_negative and today['close'] < start_positive_open:
                return "吞没阴线（1-3根最终吞没一根阳线）"
        
        return None
    
    @staticmethod
    def _calculate_amplitude(high: float, low: float, prev_close: float) -> float:
        """计算振幅"""
        if prev_close == 0:
            return 0.0
        return ((high - low) / prev_close) * 100
    
    @staticmethod
    def _get_daily_data(table_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """获取日线数据"""
        try:
            period_code = PeriodService.get_period_code('day')
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                query = f"""
                    SELECT shi_jian as date, kai_pan_jia as open, shou_pan_jia as close,
                           zui_gao_jia as high, zui_di_jia as low, cheng_jiao_liang as volume
                    FROM {table_name}
                    WHERE peroid_type = %s 
                      AND shi_jian >= %s 
                      AND shi_jian <= %s
                    ORDER BY shi_jian ASC
                """
                
                cursor.execute(query, (period_code, start_date, end_date))
                results = cursor.fetchall()
                
                daily_list = []
                for i, row in enumerate(results):
                    # 统一处理日期类型
                    date_value = row['date']
                    if isinstance(date_value, datetime):
                        date_obj = date_value
                    else:
                        try:
                            if isinstance(date_value, str):
                                date_obj = datetime.strptime(date_value.split()[0], '%Y-%m-%d')
                            else:
                                date_obj = datetime.combine(date_value, datetime.min.time())
                        except:
                            date_obj = date_value
                    
                    daily_item = {
                        'date': date_obj,
                        'open': float(row['open']) if row['open'] else 0,
                        'close': float(row['close']) if row['close'] else 0,
                        'high': float(row['high']) if row['high'] else 0,
                        'low': float(row['low']) if row['low'] else 0,
                        'volume': int(row['volume']) if row['volume'] else 0
                    }
                    # 添加前一日收盘价
                    if i > 0:
                        daily_item['prev_close'] = float(results[i-1]['close']) if results[i-1]['close'] else 0
                    daily_list.append(daily_item)
                
                return daily_list
                
        except Exception as e:
            logger.error(f"获取日线数据失败: {table_name}: {e}", exc_info=True)
            return []

