"""CR策略领域服务"""
from typing import Optional, Tuple
from domain.models.cr_point import ABCComponents
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRStrategyService:
    """CR策略领域服务 - 负责计算ABC和判断CR点"""
    
    @staticmethod
    def calculate_abc(open_price: float, high_price: float, low_price: float, close_price: float) -> ABCComponents:
        """
        计算K线的ABC组成部分
        
        Args:
            open_price: 开盘价
            high_price: 最高价
            low_price: 最低价
            close_price: 收盘价
            
        Returns:
            ABCComponents: ABC组成部分
        """
        # a（上引线）= 最高价 - max(开盘价, 收盘价)
        a = high_price - max(open_price, close_price)
        
        # b（实体）= max(开盘价, 收盘价) - min(开盘价, 收盘价)
        b = max(open_price, close_price) - min(open_price, close_price)
        
        # c（下引线）= min(开盘价, 收盘价) - 最低价
        c = min(open_price, close_price) - low_price
        
        return ABCComponents(a=a, b=b, c=c)
    
    @staticmethod
    def check_c_point_strategy_1(abc: ABCComponents, low_price: float) -> Tuple[bool, float, str]:
        """
        检查是否满足C点策略1
        
        策略1条件：
        1. a/c = 0.9~1.1
        2. b / 最低价 < 1%
        3. a ≠ 0 且 c ≠ 0
        
        Args:
            abc: ABC组成部分
            low_price: 最低价
            
        Returns:
            Tuple[bool, float, str]: (是否触发, 得分, 策略描述)
        """
        strategy_name = "策略1-上下影线均衡小实体"
        
        # 条件3：a ≠ 0 且 c ≠ 0
        if abc.a == 0 or abc.c == 0:
            logger.debug(f"{strategy_name}: a或c为0，不满足条件")
            return False, 0, strategy_name
        
        # 条件1：a/c = 0.9~1.1
        a_c_ratio = abc.a / abc.c
        if not (0.9 <= a_c_ratio <= 1.1):
            logger.debug(f"{strategy_name}: a/c={a_c_ratio:.4f}，不在0.9~1.1范围内")
            return False, 0, strategy_name
        
        # 条件2：b / 最低价 < 1%
        if low_price == 0:
            logger.debug(f"{strategy_name}: 最低价为0，数据异常")
            return False, 0, strategy_name
            
        b_low_ratio = abc.b / low_price
        if b_low_ratio >= 0.01:  # 1%
            logger.debug(f"{strategy_name}: b/最低价={b_low_ratio:.4f}，不小于1%")
            return False, 0, strategy_name
        
        # 计算得分（越接近理想值得分越高）
        # a/c越接近1得分越高，b/最低价越小得分越高
        score_a_c = 1 - abs(a_c_ratio - 1.0) / 0.1  # a/c在1.0时得分1，在0.9或1.1时得分0
        score_b_low = 1 - (b_low_ratio / 0.01)  # b/最低价为0时得分1，接近1%时得分0
        
        # 综合得分
        final_score = (score_a_c + score_b_low) / 2
        
        logger.info(f"{strategy_name}: 触发C点！a/c={a_c_ratio:.4f}, b/最低价={b_low_ratio:.4f}, 得分={final_score:.4f}")
        
        return True, final_score, strategy_name
    
    @staticmethod
    def check_r_point_strategy_1(abc: ABCComponents, high_price: float) -> Tuple[bool, float, str]:
        """
        检查是否满足R点策略1（与C点对称）
        
        策略1条件（示例，可以后续调整）：
        1. a/c = 0.9~1.1
        2. b / 最高价 < 1%
        3. a ≠ 0 且 c ≠ 0
        
        Args:
            abc: ABC组成部分
            high_price: 最高价
            
        Returns:
            Tuple[bool, float, str]: (是否触发, 得分, 策略描述)
        """
        strategy_name = "策略1-上下影线均衡小实体(卖出)"
        
        # 条件3：a ≠ 0 且 c ≠ 0
        if abc.a == 0 or abc.c == 0:
            return False, 0, strategy_name
        
        # 条件1：a/c = 0.9~1.1
        a_c_ratio = abc.a / abc.c
        if not (0.9 <= a_c_ratio <= 1.1):
            return False, 0, strategy_name
        
        # 条件2：b / 最高价 < 1%
        if high_price == 0:
            return False, 0, strategy_name
            
        b_high_ratio = abc.b / high_price
        if b_high_ratio >= 0.01:  # 1%
            return False, 0, strategy_name
        
        # 计算得分
        score_a_c = 1 - abs(a_c_ratio - 1.0) / 0.1
        score_b_high = 1 - (b_high_ratio / 0.01)
        final_score = (score_a_c + score_b_high) / 2
        
        logger.info(f"{strategy_name}: 触发R点！a/c={a_c_ratio:.4f}, b/最高价={b_high_ratio:.4f}, 得分={final_score:.4f}")
        
        return True, final_score, strategy_name

