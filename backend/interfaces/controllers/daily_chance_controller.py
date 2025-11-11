"""每日机会控制器"""
from flask import request, jsonify
from domain.repositories.daily_chance_repository import IDailyChanceRepository
from application.services.daily_chance_service import DailyChanceService
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DailyChanceController:
    """每日机会控制器"""
    
    def __init__(self):
        repository = DailyChanceRepositoryImpl()
        self.service = DailyChanceService(repository)
    
    def sync_all_stocks(self):
        """同步所有股票的每日机会数据"""
        try:
            logger.info("手动触发同步所有股票每日机会数据")
            result = self.service.sync_all_stocks_daily_chance()
            
            return ResponseBuilder.success({
                'total_stocks': result['total_stocks'],
                'success_count': result['success_count'],
                'failed_count': len(result['failed_stocks']),
                'total_saved': result['total_saved'],
                'failed_stocks': result['failed_stocks']
            }, "同步完成")
            
        except Exception as e:
            logger.error(f"同步失败: {str(e)}", exc_info=True)
            return ResponseBuilder.error(f"同步失败: {str(e)}")
    
    def sync_stock(self):
        """同步单个股票的每日机会数据"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            
            if not stock_code:
                return ResponseBuilder.error("缺少参数: stockCode", code=400)
            
            # 从股票分组中查找股票信息
            from domain.models.stock import StockGroups
            stock_groups = StockGroups()
            all_groups = stock_groups.get_all_groups()
            
            stock_name = stock_code
            stock_nature = ''
            
            for nature, stocks in all_groups.items():
                for stock in stocks:
                    if stock.code == stock_code:
                        stock_name = stock.name
                        stock_nature = nature
                        break
                if stock_nature:
                    break
            
            saved_count = self.service.sync_stock_daily_chance(stock_code, stock_name, stock_nature)
            
            return ResponseBuilder.success({
                'stock_code': stock_code,
                'saved_count': saved_count
            }, f"同步完成，保存 {saved_count} 条记录")
            
        except Exception as e:
            logger.error(f"同步失败: {str(e)}", exc_info=True)
            return ResponseBuilder.error(f"同步失败: {str(e)}")
    
    def get_daily_chance(self):
        """获取每日机会数据"""
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            start_date = data.get('startDate')
            end_date = data.get('endDate')
            date = data.get('date')
            
            if date:
                # 按日期查询
                daily_chances = self.service.get_daily_chance_by_date(date)
            elif stock_code:
                # 按股票代码查询
                daily_chances = self.service.get_daily_chance_by_stock(stock_code, start_date, end_date)
            else:
                return ResponseBuilder.error("缺少参数: stockCode 或 date", code=400)
            
            result = [dc.to_dict() for dc in daily_chances]
            
            return ResponseBuilder.success(result, f"查询成功，共 {len(result)} 条记录")
            
        except Exception as e:
            logger.error(f"查询失败: {str(e)}", exc_info=True)
            return ResponseBuilder.error(f"查询失败: {str(e)}")

