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
        last_c_point_date: Optional[datetime] = None  # 记录最近的C点日期（用于R点判断）
        
        for index, kline in enumerate(kline_data):
            # 检查C点策略1（新逻辑：基于赔率分+胜率分+插件）
            is_c_point, c_score, c_strategy, c_plugins, base_score, is_rejected = self.strategy_service.check_c_point_strategy_1(
                stock_code, 
                kline.time
            )
            
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
                
                # 获取前30个交易日数据（用于判断低位）
                daily_data_30 = []
                if index >= 29:
                    for i in range(index - 29, index + 1):
                        daily_data_30.append({
                            'high': kline_data[i].high,
                            'low': kline_data[i].low,
                            'close': kline_data[i].close
                        })
                
                # 检查策略2
                is_strategy2_c, strategy2_score, strategy2_reason = self.strategy2_service.check_strategy2(
                    stock_code=stock_code,
                    date=kline.time,
                    close_price=kline.close,
                    ma_data=ma_data,
                    macd_data=macd_data,
                    volume_type=volume_type,
                    bullish_pattern=bullish_pattern,
                    daily_data_30=daily_data_30,
                    index=index
                )
                
                # 记录所有K线的策略2评分（用于前端显示）
                date_str = kline.time.strftime('%Y-%m-%d')
                strategy2_scores[date_str] = {
                    'score': strategy2_score,
                    'reason': strategy2_reason,
                    'triggered': is_strategy2_c
                }
            
            if is_c_point:
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
                    plugins=c_plugins  # 添加插件信息
                )
                c_points.append(cr_point)
                # 记录最近的C点日期
                last_c_point_date = kline.time
            elif is_strategy2_c:
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
                    plugins=[]  # 策略2暂不使用插件结构
                )
                strategy2_c_points.append(strategy2_point)
                # 记录最近的C点日期
                last_c_point_date = kline.time
            elif is_rejected:
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
                    plugins=c_plugins
                )
                rejected_c_points.append(rejected_point)
            
            # 检查R点（使用新的插件系统）
            is_r_point, r_plugins = self.r_point_service.check_r_point(
                stock_code, 
                kline.time, 
                last_c_point_date  # 传入最近的C点日期（用于"上冲乏力"判断）
            )
            
            if is_r_point:
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
        
        # 计算总C点数（策略1 + 策略2）
        total_c_count = len(c_points) + len(strategy2_c_points)
        
        logger.info(f"CR点实时分析完成: {stock_code} - C点:{total_c_count}个 (策略1:{len(c_points)}个, 策略2:{len(strategy2_c_points)}个), 被否决:{len(rejected_c_points)}个, R点:{len(r_points)}个")
        
        # 清空缓存，释放内存
        self.strategy_service.clear_cache()
        self.r_point_service.clear_cache()
        self.strategy2_service.clear_cache()
        
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
            'strategy2_scores': strategy2_scores  # 所有K线的策略2评分
        }

