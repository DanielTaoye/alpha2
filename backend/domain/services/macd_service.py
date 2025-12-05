"""MACD技术指标计算服务 - 标准日K线MACD计算
参数配置: 快速EMA=12, 慢速EMA=26, 信号线周期=9

计算公式:
- EMA(12) = 前一日EMA(12) × 11/13 + 当日收盘价 × 2/13
- EMA(26) = 前一日EMA(26) × 25/27 + 当日收盘价 × 2/27  
- DIF = EMA(12) - EMA(26)
- DEA = 前一日DEA × 8/10 + 当日DIF × 2/10 (首日DEA使用DIF的9日SMA初始化)
- MACD柱 = (DIF - DEA) × 2
"""
from typing import List, Dict, Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MACDService:
    """MACD技术指标计算服务 - 标准日K线实现"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
        """
        计算指数移动平均线(EMA)
        
        公式: EMA = 前一日EMA × (period-1)/(period+1) + 当日价格 × 2/(period+1)
        首日EMA使用简单移动平均(SMA)初始化
        
        Args:
            prices: 价格列表
            period: 周期
            
        Returns:
            EMA值列表（与输入长度相同，前period-1个为None）
        """
        if len(prices) < period:
            return [None] * len(prices)
        
        ema = [None] * len(prices)
        # EMA平滑系数: 2/(period+1)
        multiplier = 2.0 / (period + 1)
        
        # 第一个EMA使用SMA（简单移动平均）初始化
        sma = sum(prices[:period]) / period
        ema[period - 1] = sma
        
        # 后续EMA计算: EMA[i] = 前一日EMA × (1-multiplier) + 当日价格 × multiplier
        for i in range(period, len(prices)):
            ema[i] = ema[i - 1] * (1 - multiplier) + prices[i] * multiplier
        
        return ema
    
    @staticmethod
    def calculate_dea(dif_values: List[Optional[float]], signal_period: int = 9) -> List[Optional[float]]:
        """
        计算DEA（信号线）
        
        公式: DEA = 前一日DEA × 8/10 + 当日DIF × 2/10
        首日DEA使用DIF的9日SMA初始化
        
        Args:
            dif_values: DIF值列表
            signal_period: 信号线周期，默认9
            
        Returns:
            DEA值列表（与输入长度相同）
        """
        dea = [None] * len(dif_values)
        
        # 找到第一个有效DIF的索引
        first_valid_idx = None
        for i, val in enumerate(dif_values):
            if val is not None:
                first_valid_idx = i
                break
        
        if first_valid_idx is None:
            return dea
        
        # 收集有效DIF值
        valid_dif_count = 0
        for i in range(first_valid_idx, len(dif_values)):
            if dif_values[i] is not None:
                valid_dif_count += 1
        
        if valid_dif_count < signal_period:
            return dea
        
        # DEA平滑系数: 2/10 = 0.2 (对应signal_period=9时的 2/(9+1))
        multiplier = 2.0 / (signal_period + 1)
        
        # 计算首个DEA: 使用前signal_period个有效DIF的SMA
        valid_count = 0
        sma_sum = 0
        sma_idx = None
        
        for i in range(first_valid_idx, len(dif_values)):
            if dif_values[i] is not None:
                sma_sum += dif_values[i]
                valid_count += 1
                if valid_count == signal_period:
                    sma_idx = i
                    break
        
        if sma_idx is None:
            return dea
        
        # 首日DEA = DIF的9日SMA
        dea[sma_idx] = sma_sum / signal_period
        
        # 后续DEA计算: DEA = 前一日DEA × (1-multiplier) + 当日DIF × multiplier
        for i in range(sma_idx + 1, len(dif_values)):
            if dif_values[i] is not None and dea[i - 1] is not None:
                dea[i] = dea[i - 1] * (1 - multiplier) + dif_values[i] * multiplier
        
        return dea
    
    @staticmethod
    def calculate_macd(close_prices: List[float], 
                      fast_period: int = 12, 
                      slow_period: int = 26, 
                      signal_period: int = 9) -> Dict[str, List[Optional[float]]]:
        """
        计算MACD指标 - 标准日K线实现
        
        MACD (Moving Average Convergence Divergence) - 平滑异同移动平均线
        
        计算流程:
        1. 计算EMA(12)和EMA(26)
        2. DIF = EMA(12) - EMA(26)
        3. DEA = DIF的9日EMA（首日用SMA初始化）
        4. MACD柱 = (DIF - DEA) × 2
        
        Args:
            close_prices: 收盘价列表
            fast_period: 快线周期，默认12
            slow_period: 慢线周期，默认26
            signal_period: 信号线周期，默认9
            
        Returns:
            包含dif、dea、macd的字典
        """
        n = len(close_prices)
        result = {
            'dif': [None] * n,
            'dea': [None] * n,
            'macd': [None] * n
        }
        
        # 数据不足，无法计算
        if n < slow_period:
            logger.warning(f"数据不足，无法计算MACD (需要至少{slow_period}个数据点，实际{n}个)")
            return result
        
        # Step 1: 计算快线EMA(12)和慢线EMA(26)
        ema_fast = MACDService.calculate_ema(close_prices, fast_period)
        ema_slow = MACDService.calculate_ema(close_prices, slow_period)
        
        # Step 2: 计算DIF = EMA(12) - EMA(26)
        # DIF从第slow_period个数据开始有效（索引slow_period-1）
        for i in range(slow_period - 1, n):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                result['dif'][i] = ema_fast[i] - ema_slow[i]
        
        # Step 3: 计算DEA = DIF的signal_period日EMA
        result['dea'] = MACDService.calculate_dea(result['dif'], signal_period)
        
        # Step 4: 计算MACD柱 = (DIF - DEA) × 2
        for i in range(n):
            if result['dif'][i] is not None and result['dea'][i] is not None:
                result['macd'][i] = (result['dif'][i] - result['dea'][i]) * 2
        
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

