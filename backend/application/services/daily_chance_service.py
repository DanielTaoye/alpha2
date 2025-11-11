"""每日机会应用服务"""
from typing import List, Optional
from datetime import datetime
from domain.models.daily_chance import DailyChance
from domain.models.stock import StockGroups
from domain.repositories.daily_chance_repository import IDailyChanceRepository
from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DailyChanceService:
    """每日机会应用服务"""
    
    def __init__(self, repository: IDailyChanceRepository):
        self.repository = repository
        self.api_client = DailyChanceApiClient()
        self.stock_groups = StockGroups()
    
    def sync_stock_daily_chance(self, stock_code: str, stock_name: str, stock_nature: str) -> int:
        """
        同步单个股票的每日机会数据
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            stock_nature: 股性
            
        Returns:
            保存的记录数
        """
        try:
            logger.info(f"开始同步股票每日机会数据: {stock_code} ({stock_name})")
            
            # 调用API获取数据
            api_data = self.api_client.get_daily_chance(stock_code)
            
            if not api_data:
                logger.warning(f"未获取到数据: {stock_code}")
                return 0
            
            # 转换为领域模型
            daily_chances = []
            for item in api_data:
                try:
                    # 解析日期
                    date_str = item.get('day', '')
                    if not date_str:
                        continue
                    
                    # 处理日期格式 "2024-06-07 00:00:00" -> "2024-06-07"
                    date_obj = datetime.strptime(date_str.split()[0], '%Y-%m-%d')
                    
                    # 解析赔率描述
                    win_ratio_desc = item.get('winRatioDescription', '')
                    day_score, week_score, total_score = self.api_client.parse_win_ratio_description(win_ratio_desc)
                    
                    # 创建模型
                    daily_chance = DailyChance(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        stock_nature=stock_nature,
                        date=date_obj,
                        chance=float(item.get('chance', 0)),
                        day_win_ratio_score=day_score,
                        week_win_ratio_score=week_score,
                        total_win_ratio_score=total_score,
                        support_price=float(item.get('supportPrice')) if item.get('supportPrice') else None,
                        pressure_price=float(item.get('pressurePrice')) if item.get('pressurePrice') else None
                    )
                    
                    daily_chances.append(daily_chance)
                    
                except Exception as e:
                    logger.warning(f"解析数据项失败: {item}, 错误={str(e)}")
                    continue
            
            # 批量保存
            saved_count = self.repository.save_batch(daily_chances)
            logger.info(f"同步完成: {stock_code}, 保存 {saved_count} 条记录")
            return saved_count
            
        except Exception as e:
            logger.error(f"同步股票每日机会数据失败: {stock_code}, 错误={str(e)}", exc_info=True)
            return 0
    
    def sync_all_stocks_daily_chance(self) -> dict:
        """
        同步所有股票的每日机会数据
        
        Returns:
            同步结果统计
        """
        logger.info("开始同步所有股票的每日机会数据")
        
        all_groups = self.stock_groups.get_all_groups()
        total_stocks = 0
        total_saved = 0
        failed_stocks = []
        
        for stock_nature, stocks in all_groups.items():
            logger.info(f"开始同步 {stock_nature} 组股票，共 {len(stocks)} 只")
            
            for stock in stocks:
                total_stocks += 1
                saved_count = self.sync_stock_daily_chance(stock.code, stock.name, stock_nature)
                
                if saved_count > 0:
                    total_saved += saved_count
                else:
                    failed_stocks.append(f"{stock.code}({stock.name})")
        
        result = {
            'total_stocks': total_stocks,
            'total_saved': total_saved,
            'failed_stocks': failed_stocks,
            'success_count': total_stocks - len(failed_stocks)
        }
        
        logger.info(f"同步完成: 共 {total_stocks} 只股票，成功 {result['success_count']} 只，失败 {len(failed_stocks)} 只，保存 {total_saved} 条记录")
        
        return result
    
    def get_daily_chance_by_stock(self, stock_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[DailyChance]:
        """获取股票的每日机会数据"""
        return self.repository.find_by_stock_code(stock_code, start_date, end_date)
    
    def get_daily_chance_by_date(self, date: str) -> List[DailyChance]:
        """获取指定日期的所有股票机会数据"""
        return self.repository.find_by_date(date)

