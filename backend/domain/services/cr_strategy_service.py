"""CR策略领域服务"""
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from domain.models.cr_point import ABCComponents
from domain.services.c_point_plugin_service import CPointPluginService, CPointPluginResult
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRStrategyService:
    """CR策略领域服务 - 负责计算ABC和判断CR点"""
    
    def __init__(self):
        """初始化CR策略服务"""
        from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
        self.daily_chance_repo = DailyChanceRepositoryImpl()
        self.plugin_service = CPointPluginService()  # 插件服务
        # 数据缓存
        self._daily_chance_cache = {}  # {date_str: DailyChance}
    
    def init_cache(self, stock_code: str, start_date: str, end_date: str):
        """
        初始化数据缓存（批量查询）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始初始化CR策略缓存: {stock_code} {start_date} 至 {end_date}")
        
        # 批量查询 daily_chance 数据
        daily_chance_list = self.daily_chance_repo.find_by_stock_code(stock_code, start_date, end_date)
        self._daily_chance_cache = {}
        for dc in daily_chance_list:
            from datetime import datetime
            date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
            self._daily_chance_cache[date_str] = dc
        
        logger.info(f"CR策略缓存初始化完成: daily_chance={len(self._daily_chance_cache)}条")
        
        # 同时初始化插件服务的缓存
        self.plugin_service.init_cache(stock_code, start_date, end_date)
    
    def clear_cache(self):
        """清空缓存"""
        self._daily_chance_cache = {}
        self.plugin_service.clear_cache()
    
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
    
    def check_c_point_strategy_1(self, stock_code: str, date: datetime, volume_type: Optional[str] = None, 
                                  total_win_rate_score: Optional[float] = None) -> Tuple[bool, float, str, List[Dict[str, Any]], float, bool]:
        """
        检查是否满足C点策略1（新逻辑 + 插件系统）
        
        基础层：
        - 基础分 = 赔率分（total_win_rate_score）+ 胜率分
        - 胜率分根据volume_type计算：
          * 温和放量（ABCD）任意一种：40分
          * 其他特殊型（H）：28分
          * 异常量（EF）任意一种：0分
        
        计算层（插件）：
        - 优先级高于基础分
        - 插件可以直接否决或调整分数
        - 如果最终分数 >= 70，则触发C点
        
        Args:
            stock_code: 股票代码
            date: 日期
            volume_type: 成交量类型（可选，如果不传则从数据库查询）
            total_win_rate_score: 赔率分（可选，如果不传则从数据库查询）
            
        Returns:
            Tuple[bool, float, str, List[Dict], float, bool]: 
                (是否触发, 最终分, 策略描述, 触发的插件列表, 基础分, 是否被插件否决)
        """
        strategy_name = "策略一-赔率+胜率综合评分+插件"
        
        # 如果没有传入参数，从缓存或数据库查询
        if volume_type is None or total_win_rate_score is None:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            
            # 优先使用缓存
            daily_chance = self._daily_chance_cache.get(date_str)
            if not daily_chance:
                # 缓存未命中，查询数据库
                daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            
            if not daily_chance:
                logger.debug(f"{strategy_name}: 未找到股票 {stock_code} 在 {date_str} 的daily_chance数据")
                return False, 0, strategy_name, [], 0, False
            
            volume_type = daily_chance.volume_type
            total_win_rate_score = daily_chance.total_win_ratio_score
        
        # === 基础层计算 ===
        # 赔率分
        win_ratio_score = total_win_rate_score if total_win_rate_score is not None else 0
        
        # 计算胜率分
        win_rate_score = self._calculate_win_rate_score(volume_type)
        
        # 基础总分
        base_score = win_ratio_score + win_rate_score
        
        # === 计算层（插件）===
        final_score, triggered_plugins = self.plugin_service.apply_plugins(stock_code, date, base_score)
        
        # 判断是否触发C点
        is_triggered = final_score >= 70
        
        # 判断是否被插件否决（基础分>=70但最终分<70）
        is_rejected_by_plugin = (base_score >= 70 and final_score < 70)
        
        # 格式化插件信息
        plugin_dicts = [p.to_dict() for p in triggered_plugins]
        plugin_names = [p.plugin_name for p in triggered_plugins] if triggered_plugins else []
        
        if is_triggered:
            logger.info(f"{strategy_name}: 触发C点！股票={stock_code}, 日期={date}, "
                       f"赔率分={win_ratio_score:.2f}, 胜率分={win_rate_score:.2f}, "
                       f"基础分={base_score:.2f}, 最终分={final_score:.2f}, "
                       f"成交量类型={volume_type}, 触发插件={plugin_names}")
        elif is_rejected_by_plugin:
            logger.info(f"{strategy_name}: 基础分达标但被插件否决！股票={stock_code}, 日期={date}, "
                       f"赔率分={win_ratio_score:.2f}, 胜率分={win_rate_score:.2f}, "
                       f"基础分={base_score:.2f}, 最终分={final_score:.2f}, "
                       f"成交量类型={volume_type}, 否决插件={plugin_names}")
        else:
            # 如果基础分接近70（>=60），输出info级别日志，方便调试
            if base_score >= 60:
                logger.info(f"{strategy_name}: 未触发C点(接近)。股票={stock_code}, 日期={date}, "
                           f"赔率分={win_ratio_score:.2f}, 胜率分={win_rate_score:.2f}, "
                           f"基础分={base_score:.2f}, 最终分={final_score:.2f}, "
                           f"成交量类型={volume_type}, 触发插件={plugin_names}")
            else:
                logger.debug(f"{strategy_name}: 未触发C点。股票={stock_code}, 日期={date}, "
                            f"赔率分={win_ratio_score:.2f}, 胜率分={win_rate_score:.2f}, "
                            f"基础分={base_score:.2f}, 最终分={final_score:.2f}, "
                            f"成交量类型={volume_type}, 触发插件={plugin_names}")
        
        return is_triggered, final_score, strategy_name, plugin_dicts, base_score, is_rejected_by_plugin
    
    @staticmethod
    def _calculate_win_rate_score(volume_type: Optional[str]) -> float:
        """
        根据成交量类型计算胜率分
        
        Args:
            volume_type: 成交量类型（如'A', 'B,C', 'H', 'E,F'等）
            
        Returns:
            胜率分
        """
        if not volume_type:
            return 0
        
        # 分割多个类型
        types = [t.strip() for t in volume_type.split(',')]
        
        # 异常量（E或F）优先级最高，如果包含E或F，则得0分
        if 'E' in types or 'F' in types:
            return 0
        
        # 温和放量（ABCD）任意一种，得40分
        if any(t in ['A', 'B', 'C', 'D'] for t in types):
            return 40
        
        # 其他特殊型（H），得28分
        if 'H' in types:
            return 28
        
        # 其他情况（如X、Y、Z、G等），不得分
        return 0
    
    @staticmethod
    def check_r_point_strategy_1(abc: ABCComponents, high_price: float) -> Tuple[bool, float, str]:
        """
        检查是否满足R点策略1（暂时保留原逻辑，等待后续需求）
        
        策略1条件：
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

