"""K线数据仓储实现"""
import pymysql
from typing import List
from datetime import datetime
from domain.repositories.kline_repository import IKLineRepository
from domain.models.kline import KLineData, PeriodInfo
from infrastructure.persistence.database import DatabaseConnection
from domain.services.period_service import PeriodService


class KLineRepositoryImpl(IKLineRepository):
    """K线数据仓储实现"""
    
    def get_kline_data(self, table_name: str, period_type: str, 
                      start_date: datetime, limit: int = 2000) -> List[KLineData]:
        """获取K线数据"""
        period_code = PeriodService.get_period_code(period_type)
        
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            query = f"""
                SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                       cheng_jiao_liang, liang_bi, wei_bi
                FROM {table_name}
                WHERE peroid_type = %s AND shi_jian >= %s
                ORDER BY shi_jian DESC
                LIMIT %s
            """
            
            cursor.execute(query, (period_code, start_date, limit))
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
                    volume=int(row['cheng_jiao_liang']) if row['cheng_jiao_liang'] else 0,
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

