"""CR点应用服务"""
from typing import List, Dict, Any
from datetime import datetime
from domain.models.cr_point import CRPoint, ABCComponents
from domain.models.kline import KLineData
from domain.repositories.cr_point_repository import CRPointRepository
from domain.services.cr_strategy_service import CRStrategyService
from infrastructure.persistence.cr_point_repository_impl import CRPointRepositoryImpl
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRPointService:
    """CR点应用服务"""
    
    def __init__(self):
        self.cr_repository: CRPointRepository = CRPointRepositoryImpl()
        self.strategy_service = CRStrategyService()
    
    def analyze_and_save_cr_points(self, stock_code: str, stock_name: str, kline_data: List[KLineData]) -> Dict[str, Any]:
        """
        分析K线数据并保存CR点
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            kline_data: K线数据列表
            
        Returns:
            分析结果统计
        """
        c_points = []
        r_points = []
        
        for kline in kline_data:
            # 检查C点策略1（新逻辑：基于赔率分+胜率分）
            is_c_point, c_score, c_strategy = self.strategy_service.check_c_point_strategy_1(
                stock_code, 
                kline.time
            )
            
            if is_c_point:
                # 计算ABC（用于记录）
                abc = self.strategy_service.calculate_abc(
                    kline.open,
                    kline.high,
                    kline.low,
                    kline.close
                )
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
                    strategy_name=c_strategy
                )
                
                if self.cr_repository.save(cr_point):
                    c_points.append(cr_point)
            
            # 检查R点策略1（R点逻辑稍后给出，暂时保留原逻辑）
            abc_r = self.strategy_service.calculate_abc(
                kline.open,
                kline.high,
                kline.low,
                kline.close
            )
            is_r_point, r_score, r_strategy = self.strategy_service.check_r_point_strategy_1(abc_r, kline.high)
            
            if is_r_point:
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
                    a_value=abc_r.a,
                    b_value=abc_r.b,
                    c_value=abc_r.c,
                    score=r_score,
                    strategy_name=r_strategy
                )
                
                if self.cr_repository.save(cr_point):
                    r_points.append(cr_point)
        
        logger.info(f"CR点分析完成: {stock_code} - C点:{len(c_points)}个, R点:{len(r_points)}个")
        
        return {
            'c_points_count': len(c_points),
            'r_points_count': len(r_points),
            'c_points': [cp.to_dict() for cp in c_points],
            'r_points': [rp.to_dict() for rp in r_points]
        }
    
    def get_cr_points(self, stock_code: str, point_type: str = None) -> List[Dict[str, Any]]:
        """
        获取股票的CR点
        
        Args:
            stock_code: 股票代码
            point_type: 点类型（'C'或'R'），None表示全部
            
        Returns:
            CR点列表
        """
        cr_points = self.cr_repository.find_by_stock_code(stock_code, point_type)
        return [cp.to_dict() for cp in cr_points]
    
    def get_cr_points_by_date_range(self, stock_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        根据日期范围获取CR点
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            CR点列表
        """
        cr_points = self.cr_repository.find_by_date_range(stock_code, start_date, end_date)
        return [cp.to_dict() for cp in cr_points]

