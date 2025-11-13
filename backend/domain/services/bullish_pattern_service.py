"""多头组合识别服务"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from domain.services.kline_pattern_service import KLinePatternService
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from domain.services.period_service import PeriodService
import pymysql.cursors

logger = get_logger(__name__)


class BullishPatternService:
    """多头组合识别服务"""
    
    @staticmethod
    def identify_bullish_patterns(
        stock_code: str,
        table_name: str,
        target_date: datetime
    ) -> List[str]:
        """
        识别指定日期的多头组合
        
        Args:
            stock_code: 股票代码
            table_name: 股票表名
            target_date: 目标日期
            
        Returns:
            匹配的多头组合列表，如 ["十字星+中阳线", "阳包阴"]
        """
        try:
            # 获取足够的历史数据（需要前3天的数据）
            start_date = target_date - timedelta(days=5)
            
            daily_data = BullishPatternService._get_daily_data(
                table_name, start_date, target_date
            )
            
            if not daily_data or len(daily_data) < 2:
                return []
            
            # 按日期排序（从旧到新）
            daily_data.sort(key=lambda x: x['date'])
            
            # 找到目标日期的索引
            target_idx = None
            for i, data in enumerate(daily_data):
                if data['date'].date() == target_date.date():
                    target_idx = i
                    break
            
            if target_idx is None or target_idx < 1:
                return []
            
            matched_patterns = []
            
            # 获取目标日期的数据
            today = daily_data[target_idx]
            prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None
            
            # 1. 十字星+中阳线
            pattern1 = BullishPatternService._check_pattern1(
                stock_code, prev_day, today
            )
            if pattern1:
                matched_patterns.append(pattern1)
            
            # 2. 触底反弹阳线+阳线
            pattern2 = BullishPatternService._check_pattern2(
                stock_code, prev_day, today
            )
            if pattern2:
                matched_patterns.append(pattern2)
            
            # 3. 触底反弹阴线+中阳
            pattern3 = BullishPatternService._check_pattern3(
                stock_code, prev_day, today
            )
            if pattern3:
                matched_patterns.append(pattern3)
            
            # 4. 阳包阴
            pattern4 = BullishPatternService._check_pattern4(
                stock_code, prev_day, today
            )
            if pattern4:
                matched_patterns.append(pattern4)
            
            # 5. 刺透
            pattern5 = BullishPatternService._check_pattern5(
                stock_code, prev_day, today
            )
            if pattern5:
                matched_patterns.append(pattern5)
            
            # 6. 双针探底
            pattern6 = BullishPatternService._check_pattern6(
                stock_code, daily_data, target_idx
            )
            if pattern6:
                matched_patterns.append(pattern6)
            
            # 7. 一阳穿三阴
            pattern7 = BullishPatternService._check_pattern7(
                stock_code, table_name, daily_data, target_idx
            )
            if pattern7:
                matched_patterns.append(pattern7)
            
            return matched_patterns
            
        except Exception as e:
            logger.error(f"识别多头组合失败: {stock_code} {target_date}: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _check_pattern1(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """1. 十字星+中阳线"""
        if not prev_day:
            return None
        
        # 前一天为振幅5%以上的十字星
        prev_amplitude = BullishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        # 今日为振幅5%以上的中阳线
        today_amplitude = BullishPatternService._calculate_amplitude(
            today['high'], today['low'], prev_day['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if (prev_pattern == "十字星" and prev_amplitude >= 5.0 and
            today_pattern in ["中阳线"] and today_amplitude >= 5.0):
            return "十字星+中阳线"
        
        return None
    
    @staticmethod
    def _check_pattern2(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """2. 触底反弹阳线+阳线"""
        if not prev_day:
            return None
        
        # 前一天为振幅5%以上的触底反弹十字星或触底反弹阳线
        prev_amplitude = BullishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        # 今日为振幅6%以上的阳线
        today_amplitude = BullishPatternService._calculate_amplitude(
            today['high'], today['low'], prev_day['close']
        )
        is_positive = today['close'] > today['open']
        
        if (prev_pattern in ["触底反弹十字星", "触底反弹阳线"] and prev_amplitude >= 5.0 and
            is_positive and today_amplitude >= 6.0):
            return "触底反弹阳线+阳线"
        
        return None
    
    @staticmethod
    def _check_pattern3(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """3. 触底反弹阴线+中阳"""
        if not prev_day:
            return None
        
        # 前一日为振幅5%以上的触底反弹阴线
        prev_amplitude = BullishPatternService._calculate_amplitude(
            prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
        )
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        
        # 今日为振幅6%以上的中阳线
        today_amplitude = BullishPatternService._calculate_amplitude(
            today['high'], today['low'], prev_day['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if (prev_pattern == "触底反弹阴线" and prev_amplitude >= 5.0 and
            today_pattern == "中阳线" and today_amplitude >= 6.0):
            return "触底反弹阴线+中阳"
        
        return None
    
    @staticmethod
    def _check_pattern4(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """4. 阳包阴"""
        if not prev_day:
            return None
        
        # 前一天是>5%（B>=4%）以上跌幅的阴线
        prev_abc = KLinePatternService.calculate_abc(
            prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        prev_change = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
        prev_change_pct = abs(prev_change) * 100
        
        is_prev_negative = prev_day['close'] < prev_day['open']
        prev_b_ratio = (prev_abc.b / prev_day['low']) * 100 if prev_day['low'] > 0 else 0
        
        # 今日为阳线收盘，且收盘价>=前一天开盘价
        is_today_positive = today['close'] > today['open']
        is_engulfing = today['close'] >= prev_day['open']
        
        if (is_prev_negative and prev_change_pct > 5.0 and prev_b_ratio >= 4.0 and
            is_today_positive and is_engulfing):
            return "阳包阴"
        
        return None
    
    @staticmethod
    def _check_pattern5(stock_code: str, prev_day: Optional[Dict], today: Dict) -> Optional[str]:
        """5. 刺透"""
        if not prev_day:
            return None
        
        # 前一天是>5%(B>=4%）以上跌幅的中阴线
        prev_abc = KLinePatternService.calculate_abc(
            prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        prev_change = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
        prev_change_pct = abs(prev_change) * 100
        
        prev_pattern = KLinePatternService.identify_pattern(
            stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
        )
        prev_b_ratio = (prev_abc.b / prev_day['low']) * 100 if prev_day['low'] > 0 else 0
        
        # 后一天为阳线收盘，且收盘价>前一天（开盘价+收盘价）/2
        is_today_positive = today['close'] > today['open']
        mid_price = (prev_day['open'] + prev_day['close']) / 2
        is_piercing = today['close'] > mid_price
        
        if (prev_pattern == "中阴线" and prev_change_pct > 5.0 and prev_b_ratio >= 4.0 and
            is_today_positive and is_piercing):
            return "刺透"
        
        return None
    
    @staticmethod
    def _check_pattern6(stock_code: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """6. 双针探底"""
        if target_idx < 1:
            return None
        
        # 前一天或前两天出现带下影线的K线
        prev_patterns = []
        prev_lows = []
        
        for i in range(max(0, target_idx - 2), target_idx):
            day = daily_data[i]
            amplitude = BullishPatternService._calculate_amplitude(
                day['high'], day['low'], daily_data[i-1]['close'] if i > 0 else day['close']
            )
            pattern = KLinePatternService.identify_pattern(
                stock_code, day['open'], day['close'], day['high'], day['low']
            )
            
            if amplitude > 6.0 and pattern in ["触底反弹阳线", "触底反弹阴线", "十字星"]:
                prev_patterns.append(pattern)
                prev_lows.append(day['low'])
        
        if not prev_patterns:
            return None
        
        # 当日再次出现带下影线的K线
        today = daily_data[target_idx]
        today_amplitude = BullishPatternService._calculate_amplitude(
            today['high'], today['low'], daily_data[target_idx - 1]['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if today_amplitude <= 6.0 or today_pattern not in ["触底反弹阳线", "触底反弹阴线", "十字星"]:
            return None
        
        # 两者最低价价格相差<1.5%
        today_low = today['low']
        for prev_low in prev_lows:
            if prev_low > 0:
                price_diff_pct = abs(today_low - prev_low) / prev_low * 100
                if price_diff_pct < 1.5:
                    return "双针探底"
        
        return None
    
    @staticmethod
    def _check_pattern7(stock_code: str, table_name: str, daily_data: List[Dict], target_idx: int) -> Optional[str]:
        """7. 一阳穿三阴"""
        if target_idx < 2:
            return None
        
        # 检查前2日或前3日是否为连续阴线
        start_idx = max(0, target_idx - 3)
        consecutive_negative_days = 0
        total_decline = 0.0
        volumes = []
        max_high = 0.0
        first_negative_idx = None
        
        # 从目标日期往前找连续阴线
        for i in range(target_idx - 1, start_idx - 1, -1):
            if i < 0:
                break
            day = daily_data[i]
            is_negative = day['close'] < day['open']
            
            if is_negative:
                if first_negative_idx is None:
                    first_negative_idx = i
                consecutive_negative_days += 1
                if i > 0:
                    prev_close = daily_data[i-1]['close']
                    decline = (day['close'] - prev_close) / prev_close if prev_close > 0 else 0
                    total_decline += abs(decline) * 100
                max_high = max(max_high, day['high'])
                volumes.insert(0, day.get('volume', 0))  # 从前往后插入，保持时间顺序
            else:
                # 如果遇到非阴线，且已经有连续阴线，则停止
                if consecutive_negative_days > 0:
                    break
        
        if consecutive_negative_days < 2 or total_decline <= 6.0:
            return None
        
        # 成交量呈现连续缩量（后一日成交量<前一日交易量）
        is_volume_decreasing = True
        for i in range(1, len(volumes)):
            if volumes[i] >= volumes[i-1]:
                is_volume_decreasing = False
                break
        
        if not is_volume_decreasing:
            return None
        
        # 当日出现一根放量(XY)的阳线
        today = daily_data[target_idx]
        is_today_positive = today['close'] > today['open']
        if not is_today_positive:
            return None
        
        # 检查成交量类型（需要从数据库获取）
        today_volume_type = BullishPatternService._get_volume_type(
            table_name, stock_code, daily_data[target_idx]['date']
        )
        has_xy = today_volume_type and ('X' in today_volume_type or 'Y' in today_volume_type)
        
        if not has_xy:
            return None
        
        # 当前价大于前三日的最高价
        if today['close'] > max_high:
            return "一阳穿三阴"
        
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
                    daily_item = {
                        'date': row['date'],
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
    
    @staticmethod
    def _get_volume_type(table_name: str, stock_code: str, date: datetime) -> Optional[str]:
        """获取成交量类型"""
        try:
            from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
            repository = DailyChanceRepositoryImpl()
            
            date_str = date.strftime('%Y-%m-%d')
            daily_chances = repository.find_by_stock_code(stock_code, date_str, date_str)
            
            if daily_chances and len(daily_chances) > 0:
                return daily_chances[0].volume_type
            
            return None
        except Exception as e:
            logger.error(f"获取成交量类型失败: {e}", exc_info=True)
            return None

