"""日线数据仓储实现"""
from typing import List, Optional
from datetime import datetime
from infrastructure.persistence.database import DatabaseConnection
from domain.models.stock import StockGroups
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DailyData:
    """日线数据实体"""
    def __init__(self, stock_code: str, date, open: float, high: float, low: float, 
                 close: float, volume: int, pre_close: float = 0):
        self.stock_code = stock_code
        self.date = date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.pre_close = pre_close


class DailyRepositoryImpl:
    """日线数据仓储实现"""
    
    def find_by_date(self, stock_code: str, date_str: str) -> Optional[DailyData]:
        """根据股票代码和日期查询单条日线数据"""
        try:
            # 从stock_code提取表名
            table_name = self._get_table_name(stock_code)
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                sql = f"""
                    SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang, shang_yu_bi
                    FROM `{table_name}`
                    WHERE DATE(shi_jian) = %s
                    LIMIT 1
                """
                cursor.execute(sql, (date_str,))
                row = cursor.fetchone()
                
                if row:
                    close_price = float(row[4]) if row[4] else 0  # shou_pan_jia
                    change_pct = float(row[6]) if row[6] else 0  # shang_yu_bi (涨跌幅%)
                    
                    # 从涨跌幅反推昨收价: pre_close = close / (1 + change_pct/100)
                    if close_price > 0 and change_pct != 0:
                        pre_close = close_price / (1 + change_pct / 100)
                    else:
                        pre_close = 0
                    
                    return DailyData(
                        stock_code=stock_code,
                        date=row[0] if row[0] else None,  # shi_jian
                        open=float(row[1]) if row[1] else 0,  # kai_pan_jia
                        high=float(row[2]) if row[2] else 0,  # zui_gao_jia
                        low=float(row[3]) if row[3] else 0,  # zui_di_jia
                        close=close_price,  # shou_pan_jia
                        volume=int(row[5]) if row[5] else 0,  # cheng_jiao_liang
                        pre_close=pre_close  # 从涨跌幅计算得出
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"查询日线数据失败: {e}")
            return None
    
    def find_by_date_range(self, stock_code: str, start_date: str, end_date: str) -> List[DailyData]:
        """根据日期范围查询日线数据"""
        try:
            table_name = self._get_table_name(stock_code)
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                sql = f"""
                    SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang, shang_yu_bi
                    FROM `{table_name}`
                    WHERE DATE(shi_jian) BETWEEN %s AND %s
                      AND HOUR(shi_jian) = 0 AND MINUTE(shi_jian) = 0 AND SECOND(shi_jian) = 0
                    ORDER BY shi_jian ASC
                """
                cursor.execute(sql, (start_date, end_date))
                rows = cursor.fetchall()
                
                result = []
                prev_close = 0  # 前一日收盘价
                
                for i, row in enumerate(rows):
                    close_price = float(row[4]) if row[4] else 0
                    change_pct = float(row[6]) if row[6] else 0
                    
                    # 计算pre_close的策略：
                    # 1. 如果shang_yu_bi不为NULL且不为0，从涨跌幅反推
                    # 2. 否则，使用前一日的收盘价（按时间顺序）
                    if change_pct != 0 and close_price > 0:
                        # 从涨跌幅反推昨收价
                        pre_close = close_price / (1 + change_pct / 100)
                    elif i > 0:
                        # 使用前一日的收盘价
                        pre_close = prev_close
                    else:
                        # 第一条数据，无前一日数据
                        pre_close = 0
                    
                    result.append(DailyData(
                        stock_code=stock_code,
                        date=row[0] if row[0] else None,
                        open=float(row[1]) if row[1] else 0,
                        high=float(row[2]) if row[2] else 0,
                        low=float(row[3]) if row[3] else 0,
                        close=close_price,
                        volume=int(row[5]) if row[5] else 0,
                        pre_close=pre_close
                    ))
                    
                    # 保存当前收盘价，作为下一条记录的pre_close
                    prev_close = close_price
                
                return result
                
        except Exception as e:
            logger.error(f"查询日期范围数据失败: {e}")
            return []
    
    def _get_table_name(self, stock_code: str) -> str:
        """根据股票代码获取表名"""
        try:
            # 从stock_config.json获取表名
            stock_groups = StockGroups()
            all_groups = stock_groups.get_all_groups()
            
            for group_name, stock_list in all_groups.items():
                for stock in stock_list:
                    if stock.code == stock_code:
                        return stock.table_name
            
            # 如果找不到，使用默认格式
            return f"basic_data_{stock_code.lower()}"
        except Exception as e:
            logger.error(f"获取表名失败: {e}")
            # 降级方案：使用默认格式
            return f"basic_data_{stock_code.lower()}"

