"""CR点仓储实现"""
from typing import List, Optional
from datetime import datetime
import pymysql.cursors
from domain.repositories.cr_point_repository import CRPointRepository
from domain.models.cr_point import CRPoint
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRPointRepositoryImpl(CRPointRepository):
    """CR点仓储实现"""
    
    def save(self, cr_point: CRPoint) -> bool:
        """保存CR点"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                # 使用INSERT ... ON DUPLICATE KEY UPDATE避免重复插入
                sql = """
                    INSERT INTO cr_points (
                        stock_code, stock_name, point_type, trigger_date, trigger_price,
                        open_price, high_price, low_price, close_price, volume,
                        a_value, b_value, c_value, score, strategy_name
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON DUPLICATE KEY UPDATE
                        trigger_price = VALUES(trigger_price),
                        open_price = VALUES(open_price),
                        high_price = VALUES(high_price),
                        low_price = VALUES(low_price),
                        close_price = VALUES(close_price),
                        volume = VALUES(volume),
                        a_value = VALUES(a_value),
                        b_value = VALUES(b_value),
                        c_value = VALUES(c_value),
                        score = VALUES(score),
                        strategy_name = VALUES(strategy_name)
                """
                
                cursor.execute(sql, (
                    cr_point.stock_code,
                    cr_point.stock_name,
                    cr_point.point_type,
                    cr_point.trigger_date.strftime('%Y-%m-%d') if cr_point.trigger_date else None,
                    cr_point.trigger_price,
                    cr_point.open_price,
                    cr_point.high_price,
                    cr_point.low_price,
                    cr_point.close_price,
                    cr_point.volume,
                    cr_point.a_value,
                    cr_point.b_value,
                    cr_point.c_value,
                    cr_point.score,
                    cr_point.strategy_name
                ))
                
                logger.info(f"保存CR点成功: {cr_point.stock_code} {cr_point.trigger_date} {cr_point.point_type}")
                return True
                
        except Exception as e:
            logger.error(f"保存CR点失败: {e}")
            return False
    
    def find_by_stock_code(self, stock_code: str, point_type: Optional[str] = None) -> List[CRPoint]:
        """根据股票代码查询CR点"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                if point_type:
                    sql = """
                        SELECT * FROM cr_points 
                        WHERE stock_code = %s AND point_type = %s
                        ORDER BY trigger_date DESC
                    """
                    cursor.execute(sql, (stock_code, point_type))
                else:
                    sql = """
                        SELECT * FROM cr_points 
                        WHERE stock_code = %s
                        ORDER BY trigger_date DESC
                    """
                    cursor.execute(sql, (stock_code,))
                
                results = cursor.fetchall()
                return [self._row_to_cr_point(row) for row in results]
                
        except Exception as e:
            logger.error(f"查询CR点失败: {e}")
            return []
    
    def find_by_date_range(self, stock_code: str, start_date: str, end_date: str) -> List[CRPoint]:
        """根据日期范围查询CR点"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                sql = """
                    SELECT * FROM cr_points 
                    WHERE stock_code = %s 
                    AND trigger_date BETWEEN %s AND %s
                    ORDER BY trigger_date ASC
                """
                cursor.execute(sql, (stock_code, start_date, end_date))
                
                results = cursor.fetchall()
                return [self._row_to_cr_point(row) for row in results]
                
        except Exception as e:
            logger.error(f"查询CR点失败: {e}")
            return []
    
    def delete_by_stock_and_date(self, stock_code: str, trigger_date: str) -> bool:
        """删除指定股票和日期的CR点"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = "DELETE FROM cr_points WHERE stock_code = %s AND trigger_date = %s"
                cursor.execute(sql, (stock_code, trigger_date))
                
                logger.info(f"删除CR点成功: {stock_code} {trigger_date}")
                return True
                
        except Exception as e:
            logger.error(f"删除CR点失败: {e}")
            return False
    
    def _row_to_cr_point(self, row: dict) -> CRPoint:
        """将数据库行转换为CRPoint对象"""
        return CRPoint(
            id=row['id'],
            stock_code=row['stock_code'],
            stock_name=row['stock_name'],
            point_type=row['point_type'],
            trigger_date=row['trigger_date'],
            trigger_price=float(row['trigger_price']),
            open_price=float(row['open_price']),
            high_price=float(row['high_price']),
            low_price=float(row['low_price']),
            close_price=float(row['close_price']),
            volume=int(row['volume']),
            a_value=float(row['a_value']),
            b_value=float(row['b_value']),
            c_value=float(row['c_value']),
            score=float(row['score']),
            strategy_name=row['strategy_name'],
            created_at=row['created_at']
        )

