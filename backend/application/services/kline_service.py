"""K线数据应用服务"""
from typing import List, Dict
from datetime import datetime, timedelta
from domain.repositories.kline_repository import IKLineRepository
from domain.services.period_service import PeriodService


class KLineApplicationService:
    """K线数据应用服务"""
    
    def __init__(self, kline_repository: IKLineRepository):
        self.kline_repository = kline_repository
    
    def get_kline_data(self, table_name: str, period_type: str) -> List[Dict]:
        """
        获取K线数据
        
        Args:
            table_name: 表名
            period_type: 周期类型
            
        Returns:
            K线数据列表
        """
        # 根据周期类型计算时间范围
        days = PeriodService.get_time_range_days(period_type)
        start_date = datetime.now() - timedelta(days=days)
        
        # 获取数据
        kline_list = self.kline_repository.get_kline_data(
            table_name=table_name,
            period_type=period_type,
            start_date=start_date,
            limit=2000
        )
        
        # 转换为字典列表
        return [kline.to_dict() for kline in kline_list]
    
    def get_available_periods(self, table_name: str) -> Dict[str, int]:
        """
        获取可用的周期类型
        
        Args:
            table_name: 表名
            
        Returns:
            周期类型及数据量字典
        """
        period_list = self.kline_repository.get_available_periods(table_name)
        
        # 转换为字典
        return {
            period.period_type: period.count
            for period in period_list
        }

