"""重试单个股票"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from application.services.daily_chance_service import DailyChanceService
from domain.models.stock import StockGroups
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def retry_single_stock(stock_code: str):
    """重试单个股票"""
    logger.info("=" * 60)
    logger.info(f"开始重试股票: {stock_code}")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 初始化服务
    repository = DailyChanceRepositoryImpl()
    service = DailyChanceService(repository)
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    # 查找股票信息
    stock_name = stock_code
    stock_nature = '未知'
    
    for nature, stocks in all_groups.items():
        for stock in stocks:
            if stock.code == stock_code:
                stock_name = stock.name
                stock_nature = nature
                break
        if stock_nature != '未知':
            break
    
    logger.info(f"股票信息: {stock_code} ({stock_name}), 股性: {stock_nature}")
    
    try:
        saved_count = service.sync_stock_daily_chance(stock_code, stock_name, stock_nature)
        
        if saved_count > 0:
            logger.info("=" * 60)
            logger.info(f"✅ 成功: {stock_code}, 保存 {saved_count} 条记录")
            logger.info("=" * 60)
            return True
        else:
            logger.warning("=" * 60)
            logger.warning(f"❌ 失败: {stock_code}, 未获取到数据")
            logger.warning("=" * 60)
            return False
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ 异常: {stock_code}, 错误: {str(e)}", exc_info=True)
        logger.error("=" * 60)
        return False


if __name__ == '__main__':
    stock_code = 'SZ002751'
    if len(sys.argv) > 1:
        stock_code = sys.argv[1]
    retry_single_stock(stock_code)

