"""每日机会仓储实现"""
from typing import List, Optional
from datetime import datetime
import pymysql.cursors
from domain.repositories.daily_chance_repository import IDailyChanceRepository
from domain.models.daily_chance import DailyChance
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DailyChanceRepositoryImpl(IDailyChanceRepository):
    """每日机会仓储实现"""
    
    def save(self, daily_chance: DailyChance) -> bool:
        """保存每日机会数据"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    INSERT INTO daily_chance (
                        stock_code, stock_name, stock_nature, date, chance,
                        day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
                        support_price, pressure_price, volume_type, bullish_pattern
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON DUPLICATE KEY UPDATE
                        stock_name = VALUES(stock_name),
                        stock_nature = VALUES(stock_nature),
                        chance = VALUES(chance),
                        day_win_ratio_score = VALUES(day_win_ratio_score),
                        week_win_ratio_score = VALUES(week_win_ratio_score),
                        total_win_ratio_score = VALUES(total_win_ratio_score),
                        support_price = VALUES(support_price),
                        pressure_price = VALUES(pressure_price),
                        volume_type = VALUES(volume_type),
                        bullish_pattern = VALUES(bullish_pattern)
                """
                
                cursor.execute(sql, (
                    daily_chance.stock_code,
                    daily_chance.stock_name,
                    daily_chance.stock_nature,
                    daily_chance.date.strftime('%Y-%m-%d') if daily_chance.date else None,
                    daily_chance.chance,
                    daily_chance.day_win_ratio_score,
                    daily_chance.week_win_ratio_score,
                    daily_chance.total_win_ratio_score,
                    daily_chance.support_price,
                    daily_chance.pressure_price,
                    daily_chance.volume_type,
                    daily_chance.bullish_pattern
                ))
                
                logger.debug(f"保存每日机会数据成功: {daily_chance.stock_code} {daily_chance.date}")
                return True
                
        except Exception as e:
            logger.error(f"保存每日机会数据失败: {e}", exc_info=True)
            return False
    
    def save_batch(self, daily_chances: List[DailyChance]) -> int:
        """批量保存每日机会数据"""
        if not daily_chances:
            return 0
        
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    INSERT INTO daily_chance (
                        stock_code, stock_name, stock_nature, date, chance,
                        day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
                        support_price, pressure_price, volume_type, bullish_pattern
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON DUPLICATE KEY UPDATE
                        stock_name = VALUES(stock_name),
                        stock_nature = VALUES(stock_nature),
                        chance = VALUES(chance),
                        day_win_ratio_score = VALUES(day_win_ratio_score),
                        week_win_ratio_score = VALUES(week_win_ratio_score),
                        total_win_ratio_score = VALUES(total_win_ratio_score),
                        support_price = VALUES(support_price),
                        pressure_price = VALUES(pressure_price),
                        volume_type = VALUES(volume_type),
                        bullish_pattern = VALUES(bullish_pattern)
                """
                
                values = []
                for dc in daily_chances:
                    values.append((
                        dc.stock_code,
                        dc.stock_name,
                        dc.stock_nature,
                        dc.date.strftime('%Y-%m-%d') if dc.date else None,
                        dc.chance,
                        dc.day_win_ratio_score,
                        dc.week_win_ratio_score,
                        dc.total_win_ratio_score,
                        dc.support_price,
                        dc.pressure_price,
                        dc.volume_type,
                        dc.bullish_pattern
                    ))
                
                cursor.executemany(sql, values)
                saved_count = cursor.rowcount
                logger.info(f"批量保存每日机会数据成功: {saved_count} 条记录")
                return saved_count
                
        except Exception as e:
            logger.error(f"批量保存每日机会数据失败: {e}", exc_info=True)
            return 0
    
    def find_by_stock_code(self, stock_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[DailyChance]:
        """根据股票代码查询"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                if start_date and end_date:
                    sql = """
                        SELECT * FROM daily_chance 
                        WHERE stock_code = %s AND date BETWEEN %s AND %s
                        ORDER BY date DESC
                    """
                    cursor.execute(sql, (stock_code, start_date, end_date))
                elif start_date:
                    sql = """
                        SELECT * FROM daily_chance 
                        WHERE stock_code = %s AND date >= %s
                        ORDER BY date DESC
                    """
                    cursor.execute(sql, (stock_code, start_date))
                else:
                    sql = """
                        SELECT * FROM daily_chance 
                        WHERE stock_code = %s
                        ORDER BY date DESC
                    """
                    cursor.execute(sql, (stock_code,))
                
                results = cursor.fetchall()
                return [self._row_to_daily_chance(row) for row in results]
                
        except Exception as e:
            logger.error(f"查询每日机会数据失败: {e}", exc_info=True)
            return []
    
    def find_by_date(self, date: str) -> List[DailyChance]:
        """根据日期查询"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                sql = """
                    SELECT * FROM daily_chance 
                    WHERE date = %s
                    ORDER BY stock_code
                """
                cursor.execute(sql, (date,))
                
                results = cursor.fetchall()
                return [self._row_to_daily_chance(row) for row in results]
                
        except Exception as e:
            logger.error(f"查询每日机会数据失败: {e}", exc_info=True)
            return []
    
    def find_latest_date(self, stock_code: str) -> Optional[str]:
        """获取股票最新的数据日期"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    SELECT MAX(date) as latest_date 
                    FROM daily_chance 
                    WHERE stock_code = %s
                """
                cursor.execute(sql, (stock_code,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    return result[0].strftime('%Y-%m-%d')
                return None
                
        except Exception as e:
            logger.error(f"查询最新日期失败: {e}", exc_info=True)
            return None
    
    def update_volume_type(self, stock_code: str, date: str, volume_type: str) -> bool:
        """更新成交量类型"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    UPDATE daily_chance 
                    SET volume_type = %s
                    WHERE stock_code = %s AND date = %s
                """
                
                cursor.execute(sql, (volume_type, stock_code, date))
                updated_count = cursor.rowcount
                
                if updated_count > 0:
                    logger.debug(f"更新成交量类型成功: {stock_code} {date} -> {volume_type}")
                    return True
                else:
                    logger.warning(f"未找到要更新的记录: {stock_code} {date}")
                    return False
                
        except Exception as e:
            logger.error(f"更新成交量类型失败: {e}", exc_info=True)
            return False
    
    def update_bullish_pattern_batch(self, updates: List[tuple]) -> int:
        """
        批量更新多头组合
        
        Args:
            updates: 更新列表，每个元素为 (stock_code, date, bullish_pattern)
            
        Returns:
            更新的记录数
        """
        if not updates:
            return 0
        
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    UPDATE daily_chance 
                    SET bullish_pattern = %s
                    WHERE stock_code = %s AND date = %s
                """
                
                cursor.executemany(sql, [(bp, sc, d) for sc, d, bp in updates])
                updated_count = cursor.rowcount
                
                logger.info(f"批量更新多头组合成功: {updated_count} 条记录")
                return updated_count
                
        except Exception as e:
            logger.error(f"批量更新多头组合失败: {e}", exc_info=True)
            return 0
    
    def update_volume_type_batch(self, updates: List[tuple]) -> int:
        """
        批量更新成交量类型
        
        Args:
            updates: 更新列表，每个元素为 (stock_code, date, volume_type)
            
        Returns:
            更新的记录数
        """
        if not updates:
            return 0
        
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor()
                
                sql = """
                    UPDATE daily_chance 
                    SET volume_type = %s
                    WHERE stock_code = %s AND date = %s
                """
                
                cursor.executemany(sql, [(vt, sc, d) for sc, d, vt in updates])
                updated_count = cursor.rowcount
                
                logger.info(f"批量更新成交量类型成功: {updated_count} 条记录")
                return updated_count
                
        except Exception as e:
            logger.error(f"批量更新成交量类型失败: {e}", exc_info=True)
            return 0
    
    def _row_to_daily_chance(self, row: dict) -> DailyChance:
        """将数据库行转换为DailyChance对象"""
        return DailyChance(
            id=row['id'],
            stock_code=row['stock_code'],
            stock_name=row['stock_name'],
            stock_nature=row['stock_nature'],
            date=row['date'],
            chance=float(row['chance']),
            day_win_ratio_score=float(row['day_win_ratio_score']),
            week_win_ratio_score=float(row['week_win_ratio_score']),
            total_win_ratio_score=float(row['total_win_ratio_score']),
            support_price=float(row['support_price']) if row['support_price'] else None,
            pressure_price=float(row['pressure_price']) if row['pressure_price'] else None,
            volume_type=row.get('volume_type'),
            bullish_pattern=row.get('bullish_pattern'),
            created_at=row['created_at']
        )

