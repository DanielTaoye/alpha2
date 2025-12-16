"""CR策略领域服务"""
from typing import Optional, Tuple, List, Dict, Any
import logging
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
        from domain.services.config_service import get_config_service
        self.daily_chance_repo = DailyChanceRepositoryImpl()
        self.plugin_service = CPointPluginService()  # 插件服务
        self.config_service = get_config_service()  # 配置服务
        # 数据缓存
        self._daily_chance_cache = {}  # {date_str: DailyChance}
    
    def init_cache(self, stock_code: str, start_date: str, end_date: str,
                   daily_chance_list: Optional[List] = None,
                   daily_list: Optional[List] = None):
        """
        初始化数据缓存（批量查询）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始初始化CR策略缓存: {stock_code} {start_date} 至 {end_date}")
        
        # 批量查询 daily_chance 数据（允许外部注入，避免重复IO）
        if daily_chance_list is None:
            daily_chance_list = self.daily_chance_repo.find_by_stock_code(stock_code, start_date, end_date)
        self._daily_chance_cache = {}
        for dc in daily_chance_list:
            from datetime import datetime
            date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
            self._daily_chance_cache[date_str] = dc
        
        logger.info(f"CR策略缓存初始化完成: daily_chance={len(self._daily_chance_cache)}条")
        
        # 同时初始化插件服务的缓存（复用同一份预加载数据，避免重复IO）
        self.plugin_service.init_cache(
            stock_code,
            start_date,
            end_date,
            daily_list=daily_list,
            daily_chance_list=daily_chance_list,
        )
    
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
                                  total_win_rate_score: Optional[float] = None,
                                  historical_r_points: Optional[List] = None,
                                  historical_c_points: Optional[List] = None,
                                  stock_nature: Optional[str] = None) -> Tuple[bool, float, str, List[Dict[str, Any]], float, bool]:
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
            historical_r_points: 历史R点列表（可选，用于新插件）
            historical_c_points: 历史C点列表（可选，用于新插件）
            
        Returns:
            Tuple[bool, float, str, List[Dict], float, bool]: 
                (是否触发, 最终分, 策略描述, 触发的插件列表, 基础分, 是否被插件否决)
        """
        strategy_name = "策略一-赔率+胜率综合评分+插件"

        # 性能优化：此方法会在主循环内被调用数百次；将“过程日志”降为 debug，且使用惰性格式化避免无谓字符串拼接
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("🔍 [CRStrategyService] check_c_point_strategy_1 被调用:")
            logger.debug("  - stock_code: %s", stock_code)
            logger.debug("  - date: %s", date)
            logger.debug("  - volume_type (传入): %s", volume_type)
            logger.debug("  - total_win_rate_score (传入): %s", total_win_rate_score)
            logger.debug("  - stock_nature (传入): %s", stock_nature)
        
        resolved_nature = stock_nature
        
        # 如果没有传入 total_win_rate_score，从缓存或数据库查询
        # 注意：volume_type 可以为 None（表示没有有效的放量类型），这是合法的
        if total_win_rate_score is None:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("  🔎 [CRStrategyService] 需要从数据库查询 daily_chance:")
                logger.debug("    - stock_code: %s", stock_code)
                logger.debug("    - date_str: %s", date_str)
            
            # 优先使用缓存
            daily_chance = self._daily_chance_cache.get(date_str)
            if not daily_chance:
                # 缓存未命中，查询数据库
                logger.debug("  🔎 缓存未命中，查询数据库...")
                daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date_str)
            else:
                logger.debug("  ✅ 从缓存获取到数据")
            
            if not daily_chance:
                logger.warning(f"❌ {strategy_name}: 未找到股票 {stock_code} 在 {date_str} 的daily_chance数据")
                logger.warning(f"  返回: base_score=0")
                return False, 0, strategy_name, [], 0, False
            
            # 只更新缺失的参数
            if volume_type is None:
                volume_type = daily_chance.volume_type
            if total_win_rate_score is None:
                total_win_rate_score = daily_chance.total_win_ratio_score
            if resolved_nature is None:
                resolved_nature = getattr(daily_chance, "stock_nature", None)
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("  ✅ 获取到 daily_chance:")
                logger.debug("    - volume_type: %s", volume_type)
                logger.debug("    - total_win_rate_score: %s", total_win_rate_score)
        
        resolved_nature = resolved_nature or "波段"
        logger.debug("  🧬 [Strategy1] 股性: %s", resolved_nature)
        
        # === 基础层计算 ===
        # 赔率分
        win_ratio_score = total_win_rate_score if total_win_rate_score is not None else 0
        logger.debug("  💰 [Strategy1-BaseScore] 赔率分: %s", win_ratio_score)
        
        # 计算胜率分
        win_rate_score = self._calculate_win_rate_score(volume_type)
        logger.debug("  📈 [Strategy1-BaseScore] 胜率分: %s (成交量类型: %s)", win_rate_score, volume_type)
        
        # 基础总分
        base_score = win_ratio_score + win_rate_score
        logger.debug("  🎯 [Strategy1-BaseScore] 基础总分: %s = %s + %s", base_score, win_ratio_score, win_rate_score)
        
        # === 计算层（插件）===
        final_score, triggered_plugins, force_c_point = self.plugin_service.apply_plugins(
            stock_code, date, base_score, historical_r_points, historical_c_points
        )
        
        # 从配置读取触发阈值
        threshold = self.config_service.get_strategy1_threshold(resolved_nature)
        
        # 判断是否触发C点
        # 如果插件强制发C，则直接触发；否则根据分数判断
        if force_c_point:
            is_triggered = True
        else:
            is_triggered = final_score >= threshold
        
        # 判断是否被插件否决（基础分>=阈值但最终分<阈值）
        is_rejected_by_plugin = (base_score >= threshold and final_score < threshold and not force_c_point)
        
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
        logger.debug("  📊 [WinRateScore] 计算胜率分, volume_type=%s", volume_type)
        
        if not volume_type:
            logger.debug("    ❌ volume_type为空, 返回0分")
            return 0
        
        # 分割多个类型
        types = [t.strip() for t in volume_type.split(',')]
        logger.debug("    分割后的类型列表: %s", types)
        
        # 异常量（E或F）优先级最高，如果包含E或F，则得0分
        if 'E' in types or 'F' in types:
            logger.debug("    ❌ 包含异常量(E/F), 返回0分")
            return 0
        
        # 温和放量（ABCD）任意一种，得40分
        if any(t in ['A', 'B', 'C', 'D'] for t in types):
            logger.debug("    ✅ 包含温和放量(A/B/C/D), 返回40分")
            return 40
        
        # 其他特殊型（H），得28分
        if 'H' in types:
            logger.debug("    ✅ 包含特殊型(H), 返回28分")
            return 28
        
        # 其他情况（如X、Y、Z、G等），不得分
        logger.debug("    ❌ 其他类型, 返回0分")
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

