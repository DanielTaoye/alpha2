"""K线数据应用服务"""
from typing import List, Dict
from datetime import datetime, timedelta
from domain.repositories.kline_repository import IKLineRepository
from domain.services.period_service import PeriodService
from domain.services.macd_service import MACDService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class KLineApplicationService:
    """K线数据应用服务"""
    
    def __init__(self, kline_repository: IKLineRepository):
        self.kline_repository = kline_repository
        self.macd_service = MACDService()
    
    def get_kline_data(self, table_name: str, period_type: str) -> Dict[str, any]:
        """
        获取K线数据及技术指标
        
        Args:
            table_name: 表名
            period_type: 周期类型
            
        Returns:
            包含K线数据和技术指标的字典
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
        kline_data = [kline.to_dict() for kline in kline_list]
        
        # 计算MACD技术指标
        macd_data = {}
        if kline_data:
            try:
                macd_data = self.macd_service.calculate_macd_for_kline_data(kline_data)
                logger.info(f"MACD计算成功: 股票{table_name}, 周期{period_type}, 数据点{len(kline_data)}")
            except Exception as e:
                logger.error(f"MACD计算失败: {e}")
                macd_data = {
                    'dif': [None] * len(kline_data),
                    'dea': [None] * len(kline_data),
                    'macd': [None] * len(kline_data)
                }
        
        return {
            'kline_data': kline_data,
            'macd': macd_data
        }
    
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

