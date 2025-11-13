"""K线形态识别服务"""
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class KLineABC:
    """K线ABC值（上影线、实体、下影线）"""
    a: float  # 上影线长度
    b: float  # 实体长度
    c: float  # 下影线长度
    open: float
    close: float
    high: float
    low: float


class KLinePatternService:
    """K线形态识别服务"""
    
    @staticmethod
    def calculate_abc(open_price: float, close_price: float, high_price: float, low_price: float) -> KLineABC:
        """
        计算K线的ABC值
        
        Args:
            open_price: 开盘价
            close_price: 收盘价
            high_price: 最高价
            low_price: 最低价
            
        Returns:
            KLineABC对象
        """
        max_oc = max(open_price, close_price)
        min_oc = min(open_price, close_price)
        
        a = high_price - max_oc  # 上影线
        b = max_oc - min_oc  # 实体
        c = min_oc - low_price  # 下影线
        
        return KLineABC(
            a=max(0, a),
            b=max(0, b),
            c=max(0, c),
            open=open_price,
            close=close_price,
            high=high_price,
            low=low_price
        )
    
    @staticmethod
    def is_main_board(stock_code: str) -> bool:
        """
        判断是否为主板股票
        
        Args:
            stock_code: 股票代码，如 "SH600001" 或 "SZ000001"
            
        Returns:
            True表示主板，False表示非主板（创业、科创）
        """
        # 去掉前缀，只取数字部分
        code = stock_code.upper()
        if code.startswith('SH') or code.startswith('SZ'):
            code = code[2:]
        
        # 主板：600, 000开头
        if code.startswith('600') or code.startswith('000'):
            return True
        
        # 非主板：688（科创）, 300（创业）开头
        if code.startswith('688') or code.startswith('300'):
            return False
        
        # 默认按主板处理
        return True
    
    @staticmethod
    def get_limit_up_threshold(stock_code: str) -> float:
        """
        获取涨停阈值
        
        Args:
            stock_code: 股票代码
            
        Returns:
            涨停阈值（如0.098表示9.8%）
        """
        if KLinePatternService.is_main_board(stock_code):
            return 0.098  # 主板 9.8%
        else:
            return 0.198  # 非主板 19.8%
    
    @staticmethod
    def get_limit_down_threshold(stock_code: str) -> float:
        """
        获取跌停阈值
        
        Args:
            stock_code: 股票代码
            
        Returns:
            跌停阈值（如-0.098表示-9.8%）
        """
        if KLinePatternService.is_main_board(stock_code):
            return -0.098  # 主板 -9.8%
        else:
            return -0.198  # 非主板 -19.8%
    
    @staticmethod
    def calculate_change_rate(open_price: float, close_price: float) -> float:
        """
        计算涨跌幅
        
        Args:
            open_price: 开盘价
            close_price: 收盘价
            
        Returns:
            涨跌幅（如0.098表示9.8%）
        """
        if open_price == 0:
            return 0.0
        return (close_price - open_price) / open_price
    
    @staticmethod
    def identify_pattern(
        stock_code: str,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float
    ) -> Optional[str]:
        """
        识别K线形态
        
        Args:
            stock_code: 股票代码
            open_price: 开盘价
            close_price: 收盘价
            high_price: 最高价
            low_price: 最低价
            
        Returns:
            K线形态名称，如 "小阴线"、"大阳线"、"十字星" 等
        """
        abc = KLinePatternService.calculate_abc(open_price, close_price, high_price, low_price)
        is_main = KLinePatternService.is_main_board(stock_code)
        change_rate = KLinePatternService.calculate_change_rate(open_price, close_price)
        limit_up = KLinePatternService.get_limit_up_threshold(stock_code)
        limit_down = KLinePatternService.get_limit_down_threshold(stock_code)
        
        # 计算B相对于最低价的百分比
        if low_price > 0:
            b_ratio = (abc.b / low_price) * 100
        else:
            b_ratio = 0
        
        # 计算涨跌幅百分比
        change_pct = change_rate * 100
        
        # 特殊K线优先判断
        pattern = KLinePatternService._check_special_patterns(
            abc, change_pct, limit_up, limit_down, is_main, low_price
        )
        if pattern:
            return pattern
        
        # 分歧K线
        pattern = KLinePatternService._check_divergence_patterns(abc, is_main, low_price)
        if pattern:
            return pattern
        
        # 基础K线
        pattern = KLinePatternService._check_basic_patterns(abc, is_main, b_ratio)
        if pattern:
            return pattern
        
        return None
    
    @staticmethod
    def _check_special_patterns(
        abc: KLineABC,
        change_pct: float,
        limit_up: float,
        limit_down: float,
        is_main: bool,
        low_price: float
    ) -> Optional[str]:
        """检查特殊K线形态"""
        limit_up_pct = limit_up * 100
        limit_down_pct = abs(limit_down) * 100
        
        # 一字涨停
        if change_pct >= limit_up_pct and abc.a == 0 and abc.b == 0 and abc.c == 0:
            return "一字涨停"
        
        # 一字跌停
        if change_pct <= -limit_down_pct and abc.a == 0 and abc.b == 0 and abc.c == 0:
            return "一字跌停"
        
        # T字型涨停
        if change_pct >= limit_up_pct and abc.a == 0 and abc.b == 0:
            if low_price > 0 and (abc.c / low_price) >= 0.05:
                return "T字型涨停"
        
        # T字型跌停
        if change_pct <= -limit_down_pct and abc.b == 0 and abc.c == 0:
            if low_price > 0 and abc.a > 0:
                return "T字型跌停"
        
        return None
    
    @staticmethod
    def _check_divergence_patterns(abc: KLineABC, is_main: bool, low_price: float) -> Optional[str]:
        """检查分歧K线形态"""
        if low_price == 0:
            return None
        
        b_ratio = (abc.b / low_price) * 100
        
        # 冲高回落阳线
        if (abc.a >= 2 * abc.c and abc.a >= 2 * abc.b and
            1 < b_ratio < 3.3 and abc.open < abc.close):
            return "冲高回落阳线"
        
        # 冲高回落阴线
        if (abc.a >= 2 * abc.c and abc.a >= 2 * abc.b and
            1 < b_ratio < 3.3 and abc.open > abc.close):
            return "冲高回落阴线"
        
        # 冲高回落阳十字星
        if (abc.open < abc.close and b_ratio < 2 and
            abc.c > 0 and abc.a > 2 * abc.c):
            return "冲高回落阳十字星"
        
        # 冲高回落阴十字星
        if (abc.open > abc.close and b_ratio < 2 and
            abc.c > 0 and abc.a > 2 * abc.c):
            return "冲高回落阴十字星"
        
        # 高开低走
        if abc.open > abc.close and abc.a == 0 and abc.c < 2 * abc.b:
            return "高开低走"
        
        # 触底反弹十字星
        if (abc.c >= 2 * abc.a and abc.a > 0 and
            b_ratio < 2 and abc.a > abc.b):
            return "触底反弹十字星"
        
        # 触底反弹阳线
        if abc.close > abc.open:
            if (abc.c >= 2 * abc.a and abc.a > 0 and
                b_ratio > 2 and abc.c > abc.b):
                return "触底反弹阳线"
            elif abc.a == 0 and b_ratio > 1 and abc.c > 3 * abc.b:
                return "触底反弹阳线"
        
        # 触底反弹阴线
        if abc.close < abc.open:
            if (abc.c >= 2 * abc.a and abc.a > 0 and
                b_ratio > 2 and abc.c > abc.b):
                return "触底反弹阴线"
            elif abc.a == 0 and b_ratio > 1 and abc.c > 3 * abc.b:
                return "触底反弹阴线"
        
        return None
    
    @staticmethod
    def _check_basic_patterns(abc: KLineABC, is_main: bool, b_ratio: float) -> Optional[str]:
        """检查基础K线形态"""
        change_rate = (abc.close - abc.open) / abc.open if abc.open > 0 else 0
        change_pct = change_rate * 100
        
        # 判断涨跌
        is_positive = abc.close > abc.open
        is_negative = abc.close < abc.open
        
        # 光头涨停
        limit_up_pct = 9.8 if is_main else 19.8
        if change_pct >= limit_up_pct and abc.a == 0 and abc.b > 0:
            return "光头涨停"
        
        # 光头跌停
        limit_down_pct = -9.8 if is_main else -19.8
        if change_pct <= limit_down_pct and abc.b > 0 and abc.c == 0:
            return "光头跌停"
        
        # 光头光脚中阳线
        if (is_positive and abc.a == 0 and abc.c == 0 and
            ((is_main and b_ratio > 3) or (not is_main and b_ratio > 5))):
            return "光头光脚中阳线"
        
        # 光头光脚中阴线
        if (is_negative and abc.a == 0 and abc.c == 0 and
            ((is_main and b_ratio > 3) or (not is_main and b_ratio > 5))):
            return "光头光脚中阴线"
        
        # 十字星
        if abc.a > 0 and abc.c > 0:
            ac_ratio = abc.a / abc.c if abc.c > 0 else 0
            if 0.9 <= ac_ratio <= 1.1 and b_ratio < 1:
                return "十字星"
        
        # 小阴线
        if is_negative:
            if is_main:
                if 0 < b_ratio < 1.5:
                    return "小阴线"
            else:
                if 0 < b_ratio < 3:
                    return "小阴线"
        
        # 小阳线
        if is_positive:
            if is_main:
                if 0 < b_ratio < 1.5:
                    return "小阳线"
            else:
                if 0 < b_ratio < 3:
                    return "小阳线"
        
        # 中阴线
        if is_negative:
            if is_main:
                if 1.5 <= b_ratio < 3:
                    return "中阴线"
            else:
                if 3 <= b_ratio < 5:
                    return "中阴线"
        
        # 中阳线
        if is_positive:
            if is_main:
                if 1.5 <= b_ratio < 3:
                    return "中阳线"
            else:
                if 3 <= b_ratio < 5:
                    return "中阳线"
        
        # 大阴线
        if is_negative:
            if is_main:
                if 3 <= b_ratio < 10:
                    return "大阴线"
            else:
                if 5 <= b_ratio < 20:
                    return "大阴线"
        
        # 大阳线
        if is_positive:
            if is_main:
                if 3 <= b_ratio < 10:
                    return "大阳线"
            else:
                if 5 <= b_ratio < 20:
                    return "大阳线"
        
        return None
    
    @staticmethod
    def calculate_amplitude(high_price: float, low_price: float, prev_close: float) -> float:
        """
        计算振幅
        
        振幅 = (当日最高价 - 当日最低价) / 昨日收盘价 × 100%
        
        Args:
            high_price: 当日最高价
            low_price: 当日最低价
            prev_close: 昨日收盘价
            
        Returns:
            振幅百分比（如6.5表示6.5%）
        """
        if prev_close == 0:
            return 0.0
        return ((high_price - low_price) / prev_close) * 100
    
    @staticmethod
    def get_amplitude_threshold(stock_code: str) -> float:
        """
        获取振幅阈值
        
        Args:
            stock_code: 股票代码
            
        Returns:
            振幅阈值（如6表示6%）
        """
        if KLinePatternService.is_main_board(stock_code):
            return 6.0  # 主板 6%
        else:
            return 8.0  # 非主板 8%
    
    @staticmethod
    def is_large_amplitude(stock_code: str, high_price: float, low_price: float, prev_close: float) -> bool:
        """
        判断是否为大振幅
        
        日大振幅：>6%（主板）或 >8%（非主板）
        
        Args:
            stock_code: 股票代码
            high_price: 当日最高价
            low_price: 当日最低价
            prev_close: 昨日收盘价
            
        Returns:
            True表示大振幅，False表示小振幅
        """
        amplitude = KLinePatternService.calculate_amplitude(high_price, low_price, prev_close)
        threshold = KLinePatternService.get_amplitude_threshold(stock_code)
        return amplitude > threshold
    
    @staticmethod
    def is_small_amplitude(stock_code: str, high_price: float, low_price: float, prev_close: float) -> bool:
        """
        判断是否为小振幅
        
        日小振幅：<6%（主板）或 <8%（非主板）
        
        Args:
            stock_code: 股票代码
            high_price: 当日最高价
            low_price: 当日最低价
            prev_close: 昨日收盘价
            
        Returns:
            True表示小振幅，False表示大振幅
        """
        amplitude = KLinePatternService.calculate_amplitude(high_price, low_price, prev_close)
        threshold = KLinePatternService.get_amplitude_threshold(stock_code)
        return amplitude < threshold
    
    @staticmethod
    def get_amplitude_type(stock_code: str, high_price: float, low_price: float, prev_close: float) -> str:
        """
        获取振幅类型
        
        Args:
            stock_code: 股票代码
            high_price: 当日最高价
            low_price: 当日最低价
            prev_close: 昨日收盘价
            
        Returns:
            "日大振幅" 或 "日小振幅"
        """
        if KLinePatternService.is_large_amplitude(stock_code, high_price, low_price, prev_close):
            return "日大振幅"
        else:
            return "日小振幅"

