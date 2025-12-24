"""K线数据应用服务"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta, time
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
    
    def get_kline_data(
        self,
        table_name: str,
        period_type: str,
        exclude_today: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 2000,
    ) -> Dict[str, any]:
        """
        获取K线数据及技术指标
        
        Args:
            table_name: 表名
            period_type: 周期类型
            exclude_today: 是否排除今天的数据（默认False）
            
        Returns:
            包含K线数据和技术指标的字典
        """
        # 根据周期类型计算时间范围（允许外部指定start/end覆盖，便于批量回测按区间提速）
        if start_date is None:
            days = PeriodService.get_time_range_days(period_type)
            start_date = datetime.now() - timedelta(days=days)
        
        # 获取数据
        kline_list = self.kline_repository.get_kline_data(
            table_name=table_name,
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        # 🔥 如果需要排除今天，过滤掉今天的数据
        if exclude_today and kline_list:
            from datetime import date
            today = date.today()
            kline_list = [k for k in kline_list if k.time.date() < today]
            logger.info(f"排除今天的数据后，剩余 {len(kline_list)} 条K线数据")

        # 如果指定了end_date，额外做一次兜底过滤（避免数据库时区/类型导致边界误差）
        if end_date is not None and kline_list:
            kline_list = [k for k in kline_list if k.time <= end_date]
        
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
                # 日K线计算5、10、20、30、60日均线
                if period_type == 'day':
                    ma_data = self.ma_service.calculate_ma_for_kline_data(kline_data, periods=[5, 10, 20, 30, 60])
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
    
    def predict_today_volume(self, table_name: str) -> Dict[str, any]:
        """
        预测当天的最终成交量
        
        基于最近5个交易日的数据：
        1. 计算每天开盘到当前时间的成交量平均值
        2. 计算每天全天成交量的平均值
        3. 得到比例 = 全天成交量平均 / 当前时间成交量平均
        4. 当天预测成交量 = 当天当前成交量 × 比例
        
        Args:
            table_name: 表名
            
        Returns:
            包含预测成交量的字典
        """
        # 获取最近5天的1分钟数据（包括今天）
        recent_data = self.kline_repository.get_recent_days_1min_data(table_name, days=6)
        
        if len(recent_data) < 2:
            return {
                'predicted_volume': None,
                'current_volume': None,
                'message': '数据不足，无法预测'
            }
        
        # 按日期排序
        sorted_dates = sorted(recent_data.keys())
        today = sorted_dates[-1]  # 最新的日期
        history_dates = sorted_dates[:-1]  # 历史日期（排除今天）
        
        # 获取今天的数据
        today_data = recent_data[today]
        if not today_data:
            return {
                'predicted_volume': None,
                'current_volume': None,
                'message': '今天没有数据'
            }
        
        # 获取今天的最新时间（当前时刻）
        today_latest_time = today_data[-1].time.time()
        
        # 计算今天开盘到当前的成交量
        today_current_volume = sum(kline.volume for kline in today_data)
        
        # 计算历史5天（最多5天）的同时段成交量和全天成交量
        history_current_volumes = []  # 历史同时段成交量
        history_total_volumes = []    # 历史全天成交量
        
        for hist_date in history_dates[-5:]:  # 最多取5天
            hist_data = recent_data[hist_date]
            if not hist_data:
                continue
            
            # 计算该历史日的同时段成交量（开盘到今天当前时刻）
            hist_current_vol = sum(
                kline.volume for kline in hist_data 
                if kline.time.time() <= today_latest_time
            )
            
            # 计算该历史日的全天成交量
            hist_total_vol = sum(kline.volume for kline in hist_data)
            
            if hist_current_vol > 0 and hist_total_vol > 0:
                history_current_volumes.append(hist_current_vol)
                history_total_volumes.append(hist_total_vol)
        
        if not history_current_volumes:
            return {
                'predicted_volume': None,
                'current_volume': today_current_volume,
                'message': '历史数据不足，无法预测'
            }
        
        # 计算平均值
        avg_current_volume = sum(history_current_volumes) / len(history_current_volumes)
        avg_total_volume = sum(history_total_volumes) / len(history_total_volumes)
        
        # 计算比例
        if avg_current_volume > 0:
            ratio = avg_total_volume / avg_current_volume
        else:
            return {
                'predicted_volume': None,
                'current_volume': today_current_volume,
                'message': '历史同时段成交量为0，无法预测'
            }
        
        # 预测今天的成交量
        predicted_volume = today_current_volume * ratio
        
        logger.info(f"成交量预测: 股票{table_name}, 日期{today}, "
                   f"当前成交量{today_current_volume:.2f}, 预测成交量{predicted_volume:.2f}, "
                   f"比例{ratio:.2f}, 基于{len(history_current_volumes)}天历史数据")
        
        return {
            'predicted_volume': predicted_volume,
            'current_volume': today_current_volume,
            'ratio': ratio,
            'history_days': len(history_current_volumes),
            'current_time': today_latest_time.strftime('%H:%M:%S'),
            'trade_date': today.strftime('%Y-%m-%d'),
            'message': 'success'
        }

