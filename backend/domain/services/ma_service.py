"""移动平均线(MA)计算服务"""
from typing import List, Dict, Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MAService:
    """移动平均线(MA)计算服务"""
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> List[Optional[float]]:
        """
        计算简单移动平均线(SMA - Simple Moving Average)
        
        Args:
            prices: 价格列表
            period: 周期
            
        Returns:
            SMA值列表
        """
        if len(prices) < period:
            logger.warning(f"数据不足，无法计算{period}日均线 (需要至少{period}个数据点，实际{len(prices)}个)")
            return [None] * len(prices)
        
        sma = [None] * len(prices)
        
        # 计算每个位置的SMA
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            sma[i] = sum(window) / period
        
        return sma
    
    @staticmethod
    def calculate_multiple_ma(close_prices: List[float], 
                             periods: List[int] = [5, 10, 20]) -> Dict[str, List[Optional[float]]]:
        """
        计算多条移动平均线
        
        Args:
            close_prices: 收盘价列表
            periods: 周期列表，默认[5, 10, 20]
            
        Returns:
            包含多条MA线的字典，key为'ma5', 'ma10', 'ma20'等
        """
        result = {}
        
        if not close_prices:
            logger.warning("收盘价数据为空，无法计算均线")
            return result
        
        for period in periods:
            ma_values = MAService.calculate_sma(close_prices, period)
            result[f'ma{period}'] = ma_values
            
            # 统计有效数据数量
            valid_count = sum(1 for x in ma_values if x is not None)
            logger.info(f"MA{period}计算完成: 有效数据{valid_count}个/{len(close_prices)}个")
        
        return result
    
    @staticmethod
    def calculate_ma_for_kline_data(kline_data: List[Dict], 
                                   periods: List[int] = [5, 10, 20]) -> Dict[str, List[Optional[float]]]:
        """
        为K线数据计算移动平均线
        
        Args:
            kline_data: K线数据列表，每个元素包含close字段
            periods: 周期列表，默认[5, 10, 20]
            
        Returns:
            包含多条MA线的字典
        """
        if not kline_data:
            logger.warning("K线数据为空")
            return {}
        
        # 提取收盘价
        close_prices = [float(kline['close']) for kline in kline_data]
        
        # 计算均线
        return MAService.calculate_multiple_ma(close_prices, periods)

