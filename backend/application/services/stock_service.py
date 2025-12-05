"""股票应用服务"""
from typing import Dict, List, Optional
from domain.models.stock import StockGroups, Stock
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
import pymysql.cursors

logger = get_logger(__name__)


class StockApplicationService:
    """股票应用服务"""
    
    def __init__(self):
        self.stock_groups = StockGroups()
    
    def get_all_stock_groups(self) -> Dict[str, List[Dict]]:
        """
        获取所有股票分组（59支代表性股票）
        
        Returns:
            股票分组字典
        """
        groups = self.stock_groups.get_all_groups()
        
        # 转换为前端需要的格式
        result = {}
        for group_name, stocks in groups.items():
            result[group_name] = [
                {
                    'name': stock.name,
                    'code': stock.code,
                    'table_name': stock.table_name  # 修改为table_name以匹配前端
                }
                for stock in stocks
            ]
        
        return result
    
    def search_stocks(self, keyword: str, limit: int = 100) -> List[Dict]:
        """
        从 all_stock 表搜索股票（支持股票代码和名称搜索）
        
        Args:
            keyword: 搜索关键词（股票代码或名称）
            limit: 返回结果数量限制，默认100
            
        Returns:
            股票列表，包含 code, name, nature, table_name
        """
        try:
            if not keyword or not keyword.strip():
                return []
            
            keyword = keyword.strip()
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                # 搜索未退市的股票，支持代码和名称模糊匹配
                sql = """
                    SELECT code, name, nature
                    FROM all_stock
                    WHERE (`是否退市` != 1 OR `是否退市` IS NULL)
                      AND (code LIKE %s OR name LIKE %s)
                    ORDER BY 
                        CASE 
                            WHEN code = %s THEN 1
                            WHEN code LIKE %s THEN 2
                            WHEN name LIKE %s THEN 3
                            ELSE 4
                        END,
                        code
                    LIMIT %s
                """
                
                # 构建搜索模式
                code_pattern = f"%{keyword}%"
                name_pattern = f"%{keyword}%"
                exact_code = keyword.upper()
                code_start_pattern = f"{keyword.upper()}%"
                name_start_pattern = f"{keyword}%"
                
                cursor.execute(sql, (
                    code_pattern,
                    name_pattern,
                    exact_code,
                    code_start_pattern,
                    name_start_pattern,
                    limit
                ))
                
                results = cursor.fetchall()
                
                stocks = []
                for row in results:
                    code = row['code']
                    # 生成表名：basic_data_股票代码（小写）
                    table_name = f"basic_data_{code.lower()}"
                    
                    stocks.append({
                        'code': code,
                        'name': row['name'],
                        'nature': row['nature'] or '未分类',
                        'table_name': table_name
                    })
                
                logger.info(f"搜索股票: 关键词='{keyword}', 找到 {len(stocks)} 只股票")
                return stocks
                
        except Exception as e:
            logger.error(f"搜索股票失败: {e}", exc_info=True)
            return []

