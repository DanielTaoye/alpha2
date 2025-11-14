"""MACD技术指标计算服务"""
from typing import List, Dict, Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MACDService:
    """MACD技术指标计算服务"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
        """
        计算指数移动平均线(EMA)
        
        Args:
            prices: 价格列表
            period: 周期
            
        Returns:
            EMA值列表
        """
        if len(prices) < period:
            return [None] * len(prices)
        
        ema = [None] * len(prices)
        multiplier = 2 / (period + 1)
        
        # 第一个EMA使用SMA（简单移动平均）
        sma = sum(prices[:period]) / period
        ema[period - 1] = sma
        
        # 后续EMA计算
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
        
        return ema
    
    @staticmethod
    def calculate_macd(close_prices: List[float], 
                      fast_period: int = 12, 
                      slow_period: int = 26, 
                      signal_period: int = 9) -> Dict[str, List[Optional[float]]]:
        """
        计算MACD指标
        
        MACD (Moving Average Convergence Divergence) - 平滑异同移动平均线
        - DIF (差离值): 快线EMA - 慢线EMA
        - DEA (信号线): DIF的signal_period日EMA
        - MACD柱: 2 * (DIF - DEA)
        
        Args:
            close_prices: 收盘价列表
            fast_period: 快线周期，默认12
            slow_period: 慢线周期，默认26
            signal_period: 信号线周期，默认9
            
        Returns:
            包含dif、dea、macd的字典
        """
        result = {
            'dif': [None] * len(close_prices),
            'dea': [None] * len(close_prices),
            'macd': [None] * len(close_prices)
        }
        
        # 数据不足，无法计算
        if len(close_prices) < slow_period:
            logger.warning(f"数据不足，无法计算MACD (需要至少{slow_period}个数据点，实际{len(close_prices)}个)")
            return result
        
        # 计算快线和慢线EMA
        ema_fast = MACDService.calculate_ema(close_prices, fast_period)
        ema_slow = MACDService.calculate_ema(close_prices, slow_period)
        
        # 计算DIF (快线 - 慢线)
        dif_start_index = None
        for i in range(len(close_prices)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                if dif_start_index is None:
                    dif_start_index = i
                result['dif'][i] = ema_fast[i] - ema_slow[i]
        
        # 计算DEA (DIF的signal_period日EMA)
        if dif_start_index is not None:
            # 提取有效的DIF值（从dif_start_index开始）
            valid_dif_values = []
            for i in range(dif_start_index, len(result['dif'])):
                if result['dif'][i] is not None:
                    valid_dif_values.append(result['dif'][i])
            
            # 对有效DIF值计算EMA
            if len(valid_dif_values) >= signal_period:
                dea_values = MACDService.calculate_ema(valid_dif_values, signal_period)
                
                # 将DEA值填充回结果数组
                for i, dea_val in enumerate(dea_values):
                    actual_index = dif_start_index + i
                    if actual_index < len(result['dea']) and dea_val is not None:
                        result['dea'][actual_index] = dea_val
        
        # 计算MACD柱 = 2 * (DIF - DEA)
        for i in range(len(close_prices)):
            if result['dif'][i] is not None and result['dea'][i] is not None:
                result['macd'][i] = 2 * (result['dif'][i] - result['dea'][i])
        
        # 统计有效数据数量
        valid_dif = sum(1 for x in result['dif'] if x is not None)
        valid_dea = sum(1 for x in result['dea'] if x is not None)
        valid_macd = sum(1 for x in result['macd'] if x is not None)
        
        logger.info(f"MACD计算完成: DIF有效数据{valid_dif}个, DEA有效数据{valid_dea}个, MACD柱有效数据{valid_macd}个")
        
        return result
    
    @staticmethod
    def calculate_macd_for_kline_data(kline_data: List[Dict]) -> Dict[str, List[Optional[float]]]:
        """
        为K线数据计算MACD
        
        Args:
            kline_data: K线数据列表，每个元素包含close字段
            
        Returns:
            包含dif、dea、macd的字典
        """
        if not kline_data:
            return {
                'dif': [],
                'dea': [],
                'macd': []
            }
        
        # 提取收盘价
        close_prices = [float(kline['close']) for kline in kline_data]
        
        # 计算MACD
        return MACDService.calculate_macd(close_prices)

