"""股票应用服务"""
from typing import Dict, List
from domain.models.stock import StockGroups, Stock


class StockApplicationService:
    """股票应用服务"""
    
    def __init__(self):
        self.stock_groups = StockGroups()
    
    def get_all_stock_groups(self) -> Dict[str, List[Dict]]:
        """
        获取所有股票分组
        
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
                    'table': stock.table_name
                }
                for stock in stocks
            ]
        
        return result

