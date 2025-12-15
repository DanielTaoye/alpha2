"""CR点应用服务 - 实时计算，不存储"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from domain.models.cr_point import CRPoint, ABCComponents
from domain.models.kline import KLineData
from domain.services.cr_strategy_service import CRStrategyService
from domain.services.r_point_plugin_service import RPointPluginService
from domain.services.strategy2_service import Strategy2Service
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRPointService:
    """CR点应用服务 - 实时计算C点和R点"""
    
    def __init__(self):
        self.strategy_service = CRStrategyService()
        self.r_point_service = RPointPluginService()
        self.strategy2_service = Strategy2Service()
    
    def _check_golden_c_point(self, current_index: int, kline_data: List[KLineData], 
                              strategy1_scores: Dict, strategy2_scores: Dict) -> bool:
        """
        检查是否为金色C点
        
        条件：当日策略一分数>=70 且 策略二分数>=70
        
        Args:
            current_index: 当前K线索引
            kline_data: K线数据列表
            strategy1_scores: 策略一评分字典
            strategy2_scores: 策略二评分字典
        
        Returns:
            是否为金色C点
        """
        # 获取当日日期
        date_str = kline_data[current_index].time.strftime('%Y-%m-%d')
        
        # 阈值设定
        SCORE_THRESHOLD = 70
        
        # 检查策略一分数
        strategy1_score = 0
        if date_str in strategy1_scores:
            s1_data = strategy1_scores[date_str]
            strategy1_score = s1_data.get('score', 0)
        
        # 检查策略二分数
        strategy2_score = 0
        if date_str in strategy2_scores:
            s2_data = strategy2_scores[date_str]
            strategy2_score = s2_data.get('score', 0)
        
        # 两个策略的分数都>=70才是金色C点
        is_golden = strategy1_score >= SCORE_THRESHOLD and strategy2_score >= SCORE_THRESHOLD
        
        if is_golden:
            logger.info(f"[金色C点] {date_str} 策略1分数={strategy1_score}, 策略2分数={strategy2_score}")
        
        return is_golden
    
    def analyze_cr_points(self, stock_code: str, stock_name: str, kline_data: List[KLineData],
                         ma_data: Optional[Dict] = None, macd_data: Optional[Dict] = None,
                         volume_types: Optional[Dict] = None, bullish_patterns: Optional[Dict] = None) -> Dict[str, Any]:
        """
        实时分析K线数据的CR点（不存储）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            kline_data: K线数据列表
            ma_data: MA数据 (可选，用于策略2)
            macd_data: MACD数据 (可选，用于策略2)
            volume_types: 成交量类型字典 {date_str: volume_type} (可选，用于策略2)
            bullish_patterns: 多头K线组合字典 {date_str: pattern} (可选，用于策略2)
            
        Returns:
            分析结果统计
        """
        # 性能优化：批量预加载数据到缓存
        if kline_data:
            # 计算数据日期范围（往前多取15天以支持插件查询历史数据）
            from datetime import timedelta
            start_date = (kline_data[0].time - timedelta(days=15)).strftime('%Y-%m-%d')
            end_date = kline_data[-1].time.strftime('%Y-%m-%d')
            
            logger.info(f"初始化C点和R点缓存: {stock_code} {start_date} 至 {end_date}")
            # 初始化C点策略缓存
            self.strategy_service.init_cache(stock_code, start_date, end_date)
            # 初始化R点插件缓存
            self.r_point_service.init_cache(stock_code, start_date, end_date)
        
        c_points = []
        r_points = []
        rejected_c_points = []  # 被插件否决的C点
        strategy2_c_points = []  # 策略2触发的C点
        strategy2_scores = {}  # 记录所有K线的策略2评分 {date_str: {score, reason}}
        strategy1_scores = {}  # 记录所有K线的策略1评分和插件信息 {date_str: {score, base_score, plugins}}
        last_c_point_date: Optional[datetime] = None  # 记录最近的C点日期（用于R点判断）
        
        # CR关系校验：记录最后一个有效点的类型、日期和索引
        last_valid_point_type: Optional[str] = None  # 'C' 或 'R'
        last_valid_point_date: Optional[datetime] = None
        last_valid_point_index: Optional[int] = None  # 记录最后一个C点的K线索引
        
        for index, kline in enumerate(kline_data):
            # === 第一步：先检查R点（优先级最高）===
            is_r_point, r_plugins = self.r_point_service.check_r_point(
                stock_code, 
                kline.time, 
                last_c_point_date,  # 传入最近的C点日期（用于"上冲乏力"判断）
                ma_data,  # 传入MA数据（用于高位发R插件）
                macd_data,  # 传入MACD数据（用于高位发R插件）
                index,  # 传入当前K线索引（用于高位发R插件）
                kline_data  # 传入完整K线数据（用于箱体回踩插件）
            )
            
            # 【重要】先判断R点能否真正添加（考虑CR关系规则）
            r_point_can_add = False
            if is_r_point:
                # 检查是否允许添加R点（不允许连续R）
                if last_valid_point_type == 'R':
                    # 不允许两个R点连续出现，R点被拒绝
                    r_point_can_add = False
                else:
                    # R点可以添加
                    r_point_can_add = True
            
            # 只有R点真正能添加时，才影响C点
            has_valid_r_today = r_point_can_add
            
            # === 第二步：检查C点策略1（新逻辑：基于赔率分+胜率分+插件）===
            is_c_point, c_score, c_strategy, c_plugins, base_score, is_rejected = self.strategy_service.check_c_point_strategy_1(
                stock_code, 
                kline.time,
                historical_r_points=r_points,
                historical_c_points=c_points
            )
            
            # 记录所有K线的策略1评分和插件信息（用于前端显示）
            date_str = kline.time.strftime('%Y-%m-%d')
            strategy1_scores[date_str] = {
                'score': c_score,
                'base_score': base_score,
                'plugins': c_plugins,
                'is_c_point': is_c_point,
                'is_rejected': is_rejected
            }
            
            # 计算ABC（用于记录）
            abc = self.strategy_service.calculate_abc(
                kline.open,
                kline.high,
                kline.low,
                kline.close
            )
            
            # 策略2检查（独立运行，不受策略1影响）
            is_strategy2_c = False
            strategy2_score = 0
            strategy2_reason = ""
            
            if ma_data and macd_data:
                # 准备策略2所需数据
                date_str = kline.time.strftime('%Y-%m-%d')
                volume_type = volume_types.get(date_str) if volume_types else None
                bullish_pattern = bullish_patterns.get(date_str) if bullish_patterns else None
                
                # 策略1是否被减分插件否决（赔率高胜率低/风险K线/不追涨）
                strategy1_penalty_plugins = {"赔率高胜率低", "风险K线", "不追涨"}
                strategy1_reject_by_penalty = False
                if strategy1_scores.get(date_str):
                    s1_info = strategy1_scores[date_str]
                    plugins = s1_info.get('plugins') or []
                    is_rejected_flag = s1_info.get('is_rejected', False)
                    if is_rejected_flag:
                        for p in plugins:
                            try:
                                name = p.get('pluginName') or p.get('plugin_name')
                                triggered = p.get('triggered', False)
                                if triggered and name in strategy1_penalty_plugins:
                                    strategy1_reject_by_penalty = True
                                    break
                            except Exception:
                                continue
                
                # 获取前30个交易日数据（用于判断低位）
                daily_data_30 = []
                if index >= 29:
                    for i in range(index - 29, index + 1):
                        prev_close = kline_data[i - 1].close if i - 1 >= 0 else None
                        daily_data_30.append({
                            'open': kline_data[i].open,
                            'high': kline_data[i].high,
                            'low': kline_data[i].low,
                            'close': kline_data[i].close,
                            'prev_close': prev_close
                        })
                
                # 检查策略2
                # 是否前一日有有效R点
                has_prev_valid_r = (last_valid_point_type == 'R' and
                                    last_valid_point_date is not None and
                                    (kline.time.date() - last_valid_point_date.date()).days == 1)
                
                is_strategy2_c, strategy2_score, strategy2_reason = self.strategy2_service.check_strategy2(
                    stock_code=stock_code,
                    date=kline.time,
                    close_price=kline.close,
                    ma_data=ma_data,
                    macd_data=macd_data,
                    volume_type=volume_type,
                    bullish_pattern=bullish_pattern,
                    daily_data_30=daily_data_30,
                    index=index,
                    prev_day_has_r=has_prev_valid_r,
                    strategy1_reject_by_penalty_plugins=strategy1_reject_by_penalty
                )
                
                # 记录所有K线的策略2评分（用于前端显示）
                date_str = kline.time.strftime('%Y-%m-%d')
                strategy2_scores[date_str] = {
                    'score': strategy2_score,
                    'reason': strategy2_reason,
                    'triggered': is_strategy2_c
                }
            
            if is_c_point:
                # CR关系校验：检查C点是否符合规则
                can_add_c = True
                rejection_reason = ""
                
                # 【新增逻辑】如果当天有有效的R点（R点能真正添加），策略1的C点以R点为准
                if has_valid_r_today:
                    can_add_c = False
                    rejection_reason = "当天R点触发，C和R同时触发时以R点为准"
                    logger.info(f"[CR关系校验] 策略1 C点被R点覆盖: {kline.time.strftime('%Y-%m-%d')} - {rejection_reason}")
                elif last_valid_point_type == 'C' and last_valid_point_index is not None:
                    # 两个C之间必须间隔至少2个交易日（即K线索引差>=3）
                    trading_days_diff = index - last_valid_point_index
                    if trading_days_diff < 3:
                        can_add_c = False
                        rejection_reason = f"距离上一个C点仅间隔{trading_days_diff-1}个交易日，不足2个交易日"
                        logger.info(f"[CR关系校验] C点被拒绝: {kline.time.strftime('%Y-%m-%d')} - {rejection_reason}")
                
                if can_add_c:
                    # 检查是否为金色C点
                    is_golden = self._check_golden_c_point(index, kline_data, strategy1_scores, strategy2_scores)
                    
                    # 正常触发的C点
                    cr_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='C',
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=c_score,
                        strategy_name=c_strategy,
                        plugins=c_plugins,  # 添加插件信息
                        strategy1_score=c_score,  # 策略一得分
                        strategy2_score=strategy2_score,  # 策略二得分
                        is_golden=is_golden  # 是否为金色C点
                    )
                    c_points.append(cr_point)
                    # 记录最近的C点日期
                    last_c_point_date = kline.time
                    # 更新CR关系状态
                    last_valid_point_type = 'C'
                    last_valid_point_date = kline.time
                    last_valid_point_index = index
                else:
                    # 检查是否为金色C点（即使被拒绝，也标记）
                    is_golden = self._check_golden_c_point(index, kline_data, strategy1_scores, strategy2_scores)
                    
                    # 因CR关系规则被拒绝的C点
                    rejected_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='C_REJECTED',
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=c_score,
                        strategy_name=c_strategy + f" (CR关系校验: {rejection_reason})",
                        plugins=c_plugins,
                        strategy1_score=c_score,  # 策略一得分
                        strategy2_score=strategy2_score,  # 策略二得分
                        is_golden=is_golden  # 是否为金色C点
                    )
                    rejected_c_points.append(rejected_point)
                    
            elif is_strategy2_c:
                # CR关系校验：检查C点是否符合规则
                can_add_c = True
                rejection_reason = ""
                
                # 【新增逻辑】如果当天有有效的R点（R点能真正添加），策略2的C点以R点为准
                if has_valid_r_today:
                    can_add_c = False
                    rejection_reason = "当天R点触发，策略2的C点以R点为准"
                    logger.info(f"[CR关系校验] 策略2 C点被R点覆盖: {kline.time.strftime('%Y-%m-%d')} - {rejection_reason}")
                elif last_valid_point_type == 'C' and last_valid_point_index is not None:
                    # 两个C之间必须间隔至少2个交易日（即K线索引差>=3）
                    trading_days_diff = index - last_valid_point_index
                    if trading_days_diff < 3:
                        can_add_c = False
                        rejection_reason = f"距离上一个C点仅间隔{trading_days_diff-1}个交易日，不足2个交易日"
                        logger.info(f"[CR关系校验] 策略2 C点被拒绝: {kline.time.strftime('%Y-%m-%d')} - {rejection_reason}")
                
                if can_add_c:
                    # 检查是否为金色C点
                    is_golden = self._check_golden_c_point(index, kline_data, strategy1_scores, strategy2_scores)
                    
                    # 策略2触发的C点（只添加到strategy2_c_points，不添加到c_points避免重复）
                    strategy2_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='C_STRATEGY2',  # 标记为策略2
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=strategy2_score,
                        strategy_name=f"策略2: {strategy2_reason}",
                        plugins=[],  # 策略2暂不使用插件结构
                        strategy1_score=c_score,  # 策略一得分
                        strategy2_score=strategy2_score,  # 策略二得分
                        is_golden=is_golden  # 是否为金色C点
                    )
                    strategy2_c_points.append(strategy2_point)
                    # 记录最近的C点日期
                    last_c_point_date = kline.time
                    # 更新CR关系状态
                    last_valid_point_type = 'C'
                    last_valid_point_date = kline.time
                    last_valid_point_index = index
                else:
                    # 检查是否为金色C点（即使被拒绝，也标记）
                    is_golden = self._check_golden_c_point(index, kline_data, strategy1_scores, strategy2_scores)
                    
                    # 因CR关系规则被拒绝的C点
                    rejected_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='C_REJECTED',
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=strategy2_score,
                        strategy_name=f"策略2: {strategy2_reason} (CR关系校验: {rejection_reason})",
                        plugins=[],
                        strategy1_score=c_score,  # 策略一得分
                        strategy2_score=strategy2_score,  # 策略二得分
                        is_golden=is_golden  # 是否为金色C点
                    )
                    rejected_c_points.append(rejected_point)
            elif is_rejected:
                # 检查是否为金色C点（即使被拒绝，也标记）
                is_golden = self._check_golden_c_point(index, kline_data, strategy1_scores, strategy2_scores)
                
                # 被插件否决的C点（基础分>=70但最终分<70）
                rejected_point = CRPoint(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    point_type='C_REJECTED',  # 标记为被否决
                    trigger_date=kline.time,
                    trigger_price=kline.close,
                    open_price=kline.open,
                    high_price=kline.high,
                    low_price=kline.low,
                    close_price=kline.close,
                    volume=kline.volume,
                    a_value=abc.a,
                    b_value=abc.b,
                    c_value=abc.c,
                    score=c_score,
                    strategy_name=c_strategy + " (被插件否决)",
                    plugins=c_plugins,
                    strategy1_score=c_score,  # 策略一得分
                    strategy2_score=strategy2_score,  # 策略二得分
                    is_golden=is_golden  # 是否为金色C点
                )
                rejected_c_points.append(rejected_point)
            
            # === 第三步：处理R点（已在第一步检查过，这里只处理结果）===
            if is_r_point:
                # 使用前面判断好的 r_point_can_add
                if r_point_can_add:
                    # 触发R点
                    r_strategy_name = ", ".join([p.plugin_name for p in r_plugins])
                    r_reason = " | ".join([p.reason for p in r_plugins])
                    
                    cr_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='R',
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=0,  # R点不需要分数
                        strategy_name=r_strategy_name,
                        plugins=[p.to_dict() for p in r_plugins]  # 添加插件信息
                    )
                    r_points.append(cr_point)
                    # 【关键】更新CR关系状态：当天有R点时，以R点为准
                    # 这样在后续判断"之前是否发过C"时，会把这天当作R点来计算
                    # 即使当天C点也触发了，也只显示R点（C点已被拒绝，不计入有效C点）
                    last_valid_point_type = 'R'
                    last_valid_point_date = kline.time
                    last_valid_point_index = None  # R点不参与C点间隔计算
                else:
                    # 因CR关系规则被拒绝的R点（记录在rejected_c_points中）
                    rejection_reason = "上一个点是R点，不允许RR连续出现"
                    logger.info(f"[CR关系校验] R点被拒绝: {kline.time.strftime('%Y-%m-%d')} - {rejection_reason}")
                    
                    rejected_r_point = CRPoint(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        point_type='R_REJECTED',
                        trigger_date=kline.time,
                        trigger_price=kline.close,
                        open_price=kline.open,
                        high_price=kline.high,
                        low_price=kline.low,
                        close_price=kline.close,
                        volume=kline.volume,
                        a_value=abc.a,
                        b_value=abc.b,
                        c_value=abc.c,
                        score=0,
                        strategy_name=", ".join([p.plugin_name for p in r_plugins]) + f" (CR关系校验: {rejection_reason})",
                        plugins=[p.to_dict() for p in r_plugins]
                    )
                    rejected_c_points.append(rejected_r_point)
        
        # 计算总C点数（策略1 + 策略2）
        total_c_count = len(c_points) + len(strategy2_c_points)
        
        logger.info(f"CR点实时分析完成: {stock_code} - C点:{total_c_count}个 (策略1:{len(c_points)}个, 策略2:{len(strategy2_c_points)}个), 被否决:{len(rejected_c_points)}个, R点:{len(r_points)}个")
        
        # 清空缓存，释放内存
        self.strategy_service.clear_cache()
        self.r_point_service.clear_cache()
        self.strategy2_service.clear_cache()
        
        # 日志输出：确认数据
        logger.info(f"strategy1_scores 数量: {len(strategy1_scores)}")
        if strategy1_scores:
            first_date = list(strategy1_scores.keys())[0]
            logger.info(f"示例数据 {first_date}: {strategy1_scores[first_date]}")
        
        # 🔥 调试：打印策略评分的日期范围
        if strategy1_scores:
            score_dates = sorted(strategy1_scores.keys())
            logger.info(f"🔥 策略1评分共 {len(strategy1_scores)} 条")
            if score_dates:
                logger.info(f"🔥 策略1评分日期范围: {score_dates[0]} 到 {score_dates[-1]}")
        
        if strategy2_scores:
            score_dates = sorted(strategy2_scores.keys())
            logger.info(f"🔥 策略2评分共 {len(strategy2_scores)} 条")
            if score_dates:
                logger.info(f"🔥 策略2评分日期范围: {score_dates[0]} 到 {score_dates[-1]}")
        
        return {
            'c_points_count': total_c_count,  # 总C点数（策略1+策略2）
            'r_points_count': len(r_points),
            'rejected_c_points_count': len(rejected_c_points),
            'strategy1_c_points_count': len(c_points),  # 策略1 C点数
            'strategy2_c_points_count': len(strategy2_c_points),  # 策略2 C点数
            'c_points': [cp.to_dict() for cp in c_points],  # 策略1的C点
            'r_points': [rp.to_dict() for rp in r_points],
            'rejected_c_points': [rcp.to_dict() for rcp in rejected_c_points],
            'strategy2_c_points': [s2p.to_dict() for s2p in strategy2_c_points],  # 策略2的C点
            'strategy2_scores': strategy2_scores,  # 所有K线的策略2评分
            'strategy1_scores': strategy1_scores  # 所有K线的策略1评分和插件信息
        }

