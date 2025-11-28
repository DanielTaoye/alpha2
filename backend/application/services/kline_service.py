"""K线数据应用服务"""
from typing import List, Dict
from datetime import datetime, timedelta
from domain.repositories.kline_repository import IKLineRepository
from domain.services.period_service import PeriodService
from domain.services.macd_service import MACDService
from domain.services.ma_service import MAService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class KLineApplicationService:
    """K线数据应用服务"""
    
    def __init__(self, kline_repository: IKLineRepository):
        self.kline_repository = kline_repository
        self.macd_service = MACDService()
        self.ma_service = MAService()
    
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
        
        # 计算移动平均线（MA5, MA10, MA20）
        ma_data = {}
        if kline_data:
            try:
                # 日K线计算5、10、20日均线
                if period_type == 'day':
                    ma_data = self.ma_service.calculate_ma_for_kline_data(kline_data, periods=[5, 10, 20])
                # 30分钟K线计算不同周期的均线
                elif period_type == '30min':
                    ma_data = self.ma_service.calculate_ma_for_kline_data(kline_data, periods=[10, 20, 40])
                # 周K线
                elif period_type == 'week':
                    ma_data = self.ma_service.calculate_ma_for_kline_data(kline_data, periods=[5, 10, 20])
                # 月K线
                elif period_type == 'month':
                    ma_data = self.ma_service.calculate_ma_for_kline_data(kline_data, periods=[3, 6, 12])
                
                logger.info(f"MA计算成功: 股票{table_name}, 周期{period_type}, 均线{list(ma_data.keys())}")
            except Exception as e:
                logger.error(f"MA计算失败: {e}")
                ma_data = {}
        
        return {
            'kline_data': kline_data,
            'macd': macd_data,
            'ma': ma_data
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
    
    def get_latest_day_kline(self, table_name: str) -> Dict[str, any]:
        """
        获取最新一天的K线数据（从1分钟数据聚合）
        
        Args:
            table_name: 表名
            
        Returns:
            包含聚合后的K线数据的字典
        """
        # 获取最新一天的1分钟数据
        min_data_list = self.kline_repository.get_latest_day_1min_data(table_name)
        
        if not min_data_list:
            return {
                'kline_data': None,
                'trade_date': None,
                'message': '没有找到最新交易日的数据'
            }
        
        # 聚合计算
        # 开盘价：第一根1分钟K线（9:31）的开盘价
        open_price = min_data_list[0].open
        
        # 最高价：所有1分钟K线的最高价
        high_price = max(kline.high for kline in min_data_list)
        
        # 最低价：所有1分钟K线的最低价
        low_price = min(kline.low for kline in min_data_list)
        
        # 收盘价：最后一根1分钟K线的收盘价
        close_price = min_data_list[-1].close
        
        # 成交量：所有1分钟K线的成交量之和（已在repository层除以100）
        total_volume = sum(kline.volume for kline in min_data_list)
        
        # 量比和委比取最后一根K线的值
        liangbi = min_data_list[-1].liangbi
        weibi = min_data_list[-1].weibi
        
        # 交易日期
        trade_date = min_data_list[0].time.date()
        
        # 构建聚合后的K线数据
        aggregated_kline = {
            'time': trade_date.strftime('%Y-%m-%d'),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': total_volume,
            'liangbi': liangbi,
            'weibi': weibi,
            'data_points': len(min_data_list)  # 用于调试，显示有多少个1分钟数据点
        }
        
        logger.info(f"聚合最新K线数据成功: 股票{table_name}, 日期{trade_date}, "
                   f"开{open_price:.2f} 高{high_price:.2f} 低{low_price:.2f} 收{close_price:.2f}, "
                   f"成交量{total_volume:.2f}, 数据点{len(min_data_list)}")
        
        return {
            'kline_data': aggregated_kline,
            'trade_date': trade_date.strftime('%Y-%m-%d'),
            'message': 'success'
        }

