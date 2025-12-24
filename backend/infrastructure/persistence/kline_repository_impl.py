"""K线数据仓储实现"""
import pymysql
from typing import List, Optional, Dict
from datetime import datetime, date
from collections import defaultdict
from domain.repositories.kline_repository import IKLineRepository
from domain.models.kline import KLineData, PeriodInfo
from infrastructure.persistence.database import DatabaseConnection
from domain.services.period_service import PeriodService


class KLineRepositoryImpl(IKLineRepository):
    """K线数据仓储实现"""
    
    def get_kline_data(self, table_name: str, period_type: str, 
                      start_date: datetime, end_date: Optional[datetime] = None, limit: int = 2000) -> List[KLineData]:
        """获取K线数据"""
        period_code = PeriodService.get_period_code(period_type)
        
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            if end_date is None:
                query = f"""
                    SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                           cheng_jiao_liang, liang_bi, wei_bi
                    FROM {table_name}
                    WHERE peroid_type = %s AND shi_jian >= %s
                    ORDER BY shi_jian DESC
                    LIMIT %s
                """
                cursor.execute(query, (period_code, start_date, limit))
            else:
                query = f"""
                    SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                           cheng_jiao_liang, liang_bi, wei_bi
                    FROM {table_name}
                    WHERE peroid_type = %s
                      AND shi_jian >= %s
                      AND shi_jian <= %s
                    ORDER BY shi_jian DESC
                    LIMIT %s
                """
                cursor.execute(query, (period_code, start_date, end_date, limit))
            results = cursor.fetchall()
            
            # 反转顺序，从旧到新
            results.reverse()
            
            # 转换为领域模型
            kline_list = []
            for row in results:
                kline = KLineData(
                    time=row['shi_jian'],
                    open=float(row['kai_pan_jia']) if row['kai_pan_jia'] else 0,
                    high=float(row['zui_gao_jia']) if row['zui_gao_jia'] else 0,
                    low=float(row['zui_di_jia']) if row['zui_di_jia'] else 0,
                    close=float(row['shou_pan_jia']) if row['shou_pan_jia'] else 0,
                    volume=int(row['cheng_jiao_liang']) / 100 if row['cheng_jiao_liang'] else 0,  # 成交量除以100
                    liangbi=float(row['liang_bi']) if row['liang_bi'] else 0,
                    weibi=float(row['wei_bi']) if row['wei_bi'] else 0
                )
                kline_list.append(kline)
            
            return kline_list
        finally:
            cursor.close()
            conn.close()
    
    def get_available_periods(self, table_name: str) -> List[PeriodInfo]:
        """获取可用的周期类型"""
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor()
        
        try:
            query = f"""
                SELECT DISTINCT peroid_type, COUNT(*) as count
                FROM {table_name}
                GROUP BY peroid_type
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            # 转换为领域模型
            period_list = []
            for row in results:
                db_period = row[0]
                count = row[1]
                
                # 转换为前端周期类型
                frontend_period = PeriodService.get_frontend_period(db_period)
                if frontend_period and count > 0:
                    period_list.append(PeriodInfo(
                        period_type=frontend_period,
                        count=count
                    ))
            
            return period_list
        finally:
            cursor.close()
            conn.close()
    
    def get_latest_day_1min_data(self, table_name: str, target_date: Optional[date] = None) -> List[KLineData]:
        """
        获取最新一天的1分钟级别数据
        从9:31到15:00的所有1分钟数据
        """
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 如果没有指定日期，获取最新交易日
            if target_date is None:
                date_query = f"""
                    SELECT DATE(shi_jian) as trade_date
                    FROM {table_name}
                    WHERE peroid_type = '1min'
                    ORDER BY shi_jian DESC
                    LIMIT 1
                """
                cursor.execute(date_query)
                date_result = cursor.fetchone()
                
                if not date_result:
                    return []
                
                target_date = date_result['trade_date']
            
            # 获取该日期的所有1分钟数据（从9:31到15:00）
            query = f"""
                SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                       cheng_jiao_liang, liang_bi, wei_bi
                FROM {table_name}
                WHERE peroid_type = '1min' 
                  AND DATE(shi_jian) = %s
                  AND TIME(shi_jian) >= '09:31:00'
                  AND TIME(shi_jian) <= '15:00:00'
                ORDER BY shi_jian ASC
            """
            
            cursor.execute(query, (target_date,))
            results = cursor.fetchall()
            
            # 转换为领域模型
            kline_list = []
            for row in results:
                kline = KLineData(
                    time=row['shi_jian'],
                    open=float(row['kai_pan_jia']) if row['kai_pan_jia'] else 0,
                    high=float(row['zui_gao_jia']) if row['zui_gao_jia'] else 0,
                    low=float(row['zui_di_jia']) if row['zui_di_jia'] else 0,
                    close=float(row['shou_pan_jia']) if row['shou_pan_jia'] else 0,
                    volume=int(row['cheng_jiao_liang']) / 100 if row['cheng_jiao_liang'] else 0,  # 成交量除以100
                    liangbi=float(row['liang_bi']) if row['liang_bi'] else 0,
                    weibi=float(row['wei_bi']) if row['wei_bi'] else 0
                )
                kline_list.append(kline)
            
            return kline_list
        finally:
            cursor.close()
            conn.close()
    
    def get_recent_days_1min_data(self, table_name: str, days: int = 5) -> Dict[date, List[KLineData]]:
        """获取最近N个交易日的1分钟级别数据"""
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 先获取最近N个交易日的日期列表
            date_query = f"""
                SELECT DISTINCT DATE(shi_jian) as trade_date
                FROM {table_name}
                WHERE peroid_type = '1min'
                ORDER BY trade_date DESC
                LIMIT %s
            """
            cursor.execute(date_query, (days,))
            date_results = cursor.fetchall()
            
            if not date_results:
                return {}
            
            # 获取这些日期的所有1分钟数据
            dates = [row['trade_date'] for row in date_results]
            
            query = f"""
                SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                       cheng_jiao_liang, liang_bi, wei_bi
                FROM {table_name}
                WHERE peroid_type = '1min' 
                  AND DATE(shi_jian) IN ({','.join(['%s'] * len(dates))})
                  AND TIME(shi_jian) >= '09:31:00'
                  AND TIME(shi_jian) <= '15:00:00'
                ORDER BY shi_jian ASC
            """
            
            cursor.execute(query, dates)
            results = cursor.fetchall()
            
            # 按日期分组
            data_by_date = defaultdict(list)
            for row in results:
                trade_date = row['shi_jian'].date()
                kline = KLineData(
                    time=row['shi_jian'],
                    open=float(row['kai_pan_jia']) if row['kai_pan_jia'] else 0,
                    high=float(row['zui_gao_jia']) if row['zui_gao_jia'] else 0,
                    low=float(row['zui_di_jia']) if row['zui_di_jia'] else 0,
                    close=float(row['shou_pan_jia']) if row['shou_pan_jia'] else 0,
                    volume=int(row['cheng_jiao_liang']) / 100 if row['cheng_jiao_liang'] else 0,
                    liangbi=float(row['liang_bi']) if row['liang_bi'] else 0,
                    weibi=float(row['wei_bi']) if row['wei_bi'] else 0
                )
                data_by_date[trade_date].append(kline)
            
            return dict(data_by_date)
        finally:
            cursor.close()
            conn.close()

