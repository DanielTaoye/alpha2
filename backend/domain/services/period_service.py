"""周期服务 - 领域服务"""
from infrastructure.config.app_config import PERIOD_TYPE_MAP, TIME_RANGE_CONFIG


class PeriodService:
    """周期服务"""
    
    @staticmethod
    def get_period_code(period_type: str) -> str:
        """
        获取周期代码（前端周期类型 -> 数据库字段值）
        
        Args:
            period_type: 前端周期类型
            
        Returns:
            数据库周期代码
        """
        return PERIOD_TYPE_MAP.get(period_type, '1day')
    
    @staticmethod
    def get_frontend_period(db_period: str) -> str:
        """
        获取前端周期类型（数据库字段值 -> 前端周期类型）
        
        Args:
            db_period: 数据库周期代码
            
        Returns:
            前端周期类型
        """
        period_map_reverse = {v: k for k, v in PERIOD_TYPE_MAP.items()}
        return period_map_reverse.get(db_period, 'day')
    
    @staticmethod
    def get_time_range_days(period_type: str) -> int:
        """
        获取周期的时间范围（天数）
        
        Args:
            period_type: 周期类型
            
        Returns:
            天数
        """
        return TIME_RANGE_CONFIG.get(period_type, 730)

