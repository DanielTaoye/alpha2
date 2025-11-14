"""CR点应用服务 - 实时计算，不存储"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from domain.models.cr_point import CRPoint, ABCComponents
from domain.models.kline import KLineData
from domain.services.cr_strategy_service import CRStrategyService
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRPointService:
    """CR点应用服务 - 实时计算C点和R点"""
    
    def __init__(self):
        self.strategy_service = CRStrategyService()
        self.r_point_service = RPointPluginService()
    
    def analyze_cr_points(self, stock_code: str, stock_name: str, kline_data: List[KLineData]) -> Dict[str, Any]:
        """
        实时分析K线数据的CR点（不存储）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            kline_data: K线数据列表
            
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
        last_c_point_date: Optional[datetime] = None  # 记录最近的C点日期（用于R点判断）
        
        for kline in kline_data:
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
        
        logger.info(f"CR点实时分析完成: {stock_code} - C点:{len(c_points)}个, 被否决:{len(rejected_c_points)}个, R点:{len(r_points)}个")
        
        # 清空缓存，释放内存
        self.strategy_service.clear_cache()
        self.r_point_service.clear_cache()
        
        return {
            'c_points_count': len(c_points),
            'r_points_count': len(r_points),
            'rejected_c_points_count': len(rejected_c_points),
            'c_points': [cp.to_dict() for cp in c_points],
            'r_points': [rp.to_dict() for rp in r_points],
            'rejected_c_points': [rcp.to_dict() for rcp in rejected_c_points]  # 返回被否决的C点
        }

