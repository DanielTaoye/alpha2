"""交易日历服务"""
import os
import pandas as pd
from datetime import datetime, date, time, timedelta
from typing import Optional
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class TradingCalendarService:
    """交易日历服务"""
    
    _instance = None
    _calendar_df = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._load_calendar()
        return cls._instance
    
    @classmethod
    def _load_calendar(cls):
        """加载交易日历"""
        try:
            # 获取当前文件所在目录（domain/services）
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 往上两级到backend目录
            backend_dir = os.path.dirname(os.path.dirname(current_dir))
            calendar_path = os.path.join(backend_dir, 'trade_calendar_sse.csv')
            
            cls._calendar_df = pd.read_csv(calendar_path)
            logger.info(f"交易日历加载成功，共 {len(cls._calendar_df)} 条记录")
        except Exception as e:
            logger.error(f"交易日历加载失败: {e}", exc_info=True)
            cls._calendar_df = None
    
    @classmethod
    def is_trading_day(cls, check_date: date) -> bool:
        """
        判断指定日期是否是交易日
        
        Args:
            check_date: 要检查的日期
            
        Returns:
            True表示是交易日，False表示不是
        """
        if cls._calendar_df is None:
            # 如果日历未加载，默认周一到周五为交易日
            return check_date.weekday() < 5
        
        try:
            date_str = check_date.strftime('%Y%m%d')
            row = cls._calendar_df[cls._calendar_df['cal_date'] == int(date_str)]
            
            if not row.empty:
                is_open = row.iloc[0]['is_open']
                return bool(is_open == 1)
            
            # 如果找不到该日期，默认周一到周五为交易日
            return check_date.weekday() < 5
        except Exception as e:
            logger.error(f"判断交易日失败: {e}")
            return check_date.weekday() < 5
    
    @classmethod
    def is_in_trading_time(cls, check_time: Optional[datetime] = None) -> bool:
        """
        判断是否在交易时间内
        
        交易时间：
        - 上午：09:30 - 11:30
        - 下午：13:00 - 15:00
        
        Args:
            check_time: 要检查的时间，如果为None则使用当前时间
            
        Returns:
            True表示在交易时间内，False表示不在
        """
        if check_time is None:
            check_time = datetime.now()
        
        current_time = check_time.time()
        
        # 上午交易时间：09:30 - 11:30
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        
        # 下午交易时间：13:00 - 15:00
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        return is_morning or is_afternoon
    
    @classmethod
    def should_use_predicted_volume(cls, check_datetime: Optional[datetime] = None) -> bool:
        """
        判断是否应该使用预测成交量（而不是数据库的历史成交量）
        
        只有当满足以下所有条件时，才使用预测成交量：
        1. 今天是交易日
        2. 当前时间在交易时间内（09:30-15:00）
        
        Args:
            check_datetime: 要检查的时间，如果为None则使用当前时间
            
        Returns:
            True表示应该使用预测成交量，False表示使用数据库的历史成交量
        """
        if check_datetime is None:
            check_datetime = datetime.now()
        
        # 检查是否是交易日
        if not cls.is_trading_day(check_datetime.date()):
            return False
        
        # 检查是否在交易时间内
        if not cls.is_in_trading_time(check_datetime):
            return False
        
        return True
    
    @classmethod
    def get_today_trade_date(cls) -> str:
        """
        获取今天的交易日期（YYYY-MM-DD格式）
        
        如果今天是交易日，返回今天的日期
        否则返回最近的上一个交易日
        
        Returns:
            交易日期字符串
        """
        today = date.today()
        
        # 如果今天是交易日，直接返回
        if cls.is_trading_day(today):
            return today.strftime('%Y-%m-%d')

    # =====================
    # 交易日工具（回测/调度通用）
    # =====================
    @classmethod
    def get_next_trading_day(cls, from_date: date) -> date:
        """
        获取 from_date 之后（不含当日）的下一个交易日
        """
        d = from_date + timedelta(days=1)
        for _ in range(366):  # 最多查一年，避免死循环
            if cls.is_trading_day(d):
                return d
            d += timedelta(days=1)
        return d

    @classmethod
    def add_trading_days(cls, from_date: date, trading_days: int) -> date:
        """
        从 from_date 开始往后推进 N 个交易日，返回对应日期（不要求 from_date 自身是交易日）

        例：
        - trading_days=0：返回 from_date（原样）
        - trading_days=1：返回 from_date 之后的第1个交易日
        """
        if trading_days <= 0:
            return from_date

        d = from_date
        remaining = trading_days
        for _ in range(trading_days + 366):  # 预留冗余
            d = cls.get_next_trading_day(d)
            remaining -= 1
            if remaining <= 0:
                return d
        return d
        
        # 否则往前查找最近的交易日
        if cls._calendar_df is None:
            # 如果日历未加载，简单地往前推到周五
            days_back = (today.weekday() - 4) % 7
            if days_back == 0:
                days_back = 3  # 如果今天是周六，往前推到周五
            prev_day = today - timedelta(days=days_back)
            return prev_day.strftime('%Y-%m-%d')
        
        try:
            # 从交易日历中查找
            for i in range(1, 10):  # 最多往前查10天
                check_date = today - timedelta(days=i)
                if cls.is_trading_day(check_date):
                    return check_date.strftime('%Y-%m-%d')
            
            # 如果还找不到，返回今天
            return today.strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"获取交易日期失败: {e}")
            return today.strftime('%Y-%m-%d')

