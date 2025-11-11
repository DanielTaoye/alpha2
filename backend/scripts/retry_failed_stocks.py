"""重试失败的股票同步"""
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


def retry_failed_stocks():
    """重试失败的股票"""
    # 失败的股票代码列表
    failed_stocks = [
        'SH603556',  # 海兴电力
        'SZ301039',  # 中集车辆
        'SZ300058',  # 蓝色光标
        'SH600458',  # 时代新材
        'SH603298',  # 杭叉集团
        'SZ000786',  # 北新建材
        'SH688512',  # 慧智微-U
        'SH600579',  # 中化装备
        'SZ002751',  # 易尚退
        'SZ301448',  # 开创电气
        'SZ002625',  # 光启技术
    ]
    
    logger.info("=" * 60)
    logger.info("开始重试失败的股票同步")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"失败股票数: {len(failed_stocks)}")
    logger.info("=" * 60)
    
    # 初始化服务
    repository = DailyChanceRepositoryImpl()
    service = DailyChanceService(repository)
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    # 创建股票代码到信息的映射
    stock_info_map = {}
    for stock_nature, stocks in all_groups.items():
        for stock in stocks:
            stock_info_map[stock.code] = {
                'name': stock.name,
                'nature': stock_nature
            }
    
    success_count = 0
    failed_count = 0
    total_saved = 0
    
    for stock_code in failed_stocks:
        try:
            stock_info = stock_info_map.get(stock_code, {'name': stock_code, 'nature': '未知'})
            stock_name = stock_info['name']
            stock_nature = stock_info['nature']
            
            logger.info(f"正在同步: {stock_code} ({stock_name})")
            saved_count = service.sync_stock_daily_chance(stock_code, stock_name, stock_nature)
            
            if saved_count > 0:
                success_count += 1
                total_saved += saved_count
                logger.info(f"✅ 成功: {stock_code}, 保存 {saved_count} 条记录")
            else:
                failed_count += 1
                logger.warning(f"❌ 失败: {stock_code}, 未获取到数据")
                
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ 异常: {stock_code}, 错误: {str(e)}", exc_info=True)
    
    # 输出结果
    logger.info("=" * 60)
    logger.info("重试完成")
    logger.info(f"成功: {success_count} 只")
    logger.info(f"失败: {failed_count} 只")
    logger.info(f"保存记录数: {total_saved}")
    logger.info("=" * 60)


if __name__ == '__main__':
    retry_failed_stocks()

