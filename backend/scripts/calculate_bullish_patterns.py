"""批量计算历史多头组合脚本"""
import sys
import os
from datetime import datetime
from typing import List, Dict

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from domain.services.bullish_pattern_service import BullishPatternService
from domain.models.stock import StockGroups
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def get_all_stocks() -> List[Dict]:
    """获取所有股票信息"""
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    stocks = []
    for group_name, stock_list in all_groups.items():
        for stock in stock_list:
            stocks.append({
                'code': stock.code,
                'name': stock.name,
                'table': stock.table_name,
                'nature': group_name
            })
    
    return stocks


def calculate_stock_bullish_patterns(
    stock_code: str,
    stock_name: str,
    table_name: str,
    repository: DailyChanceRepositoryImpl,
    start_date: datetime = None,
    end_date: datetime = None
) -> int:
    """
    计算单个股票的历史多头组合
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        table_name: 表名
        repository: 仓储实例
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        
    Returns:
        更新的记录数
    """
    try:
        logger.info(f"开始计算股票多头组合: {stock_code} ({stock_name})")
        
        # 获取该股票在daily_chance表中的所有日期
        daily_chances = repository.find_by_stock_code(stock_code)
        
        if not daily_chances:
            logger.warning(f"股票 {stock_code} 在daily_chance表中没有数据")
            return 0
        
        # 过滤日期范围
        if start_date:
            daily_chances = [dc for dc in daily_chances if dc.date and dc.date >= start_date]
        if end_date:
            daily_chances = [dc for dc in daily_chances if dc.date and dc.date <= end_date]
        
        if not daily_chances:
            logger.warning(f"股票 {stock_code} 在指定日期范围内没有数据")
            return 0
        
        logger.info(f"股票 {stock_code} 共有 {len(daily_chances)} 条记录需要计算")
        
        # 准备批量更新数据
        updates = []
        for dc in daily_chances:
            if dc.date:
                # 识别多头组合
                patterns = BullishPatternService.identify_bullish_patterns(
                    stock_code=stock_code,
                    table_name=table_name,
                    target_date=dc.date
                )
                
                if patterns:
                    # 多个组合用逗号连接
                    bullish_pattern = ','.join(patterns)
                    date_str = dc.date.strftime('%Y-%m-%d') if isinstance(dc.date, datetime) else str(dc.date)
                    updates.append((stock_code, date_str, bullish_pattern))
        
        if not updates:
            logger.warning(f"股票 {stock_code} 没有需要更新的记录")
            return 0
        
        # 批量更新
        updated_count = repository.update_bullish_pattern_batch(updates)
        logger.info(f"股票 {stock_code} 成功更新 {updated_count} 条记录的多头组合")
        
        return updated_count
        
    except Exception as e:
        logger.error(f"计算股票 {stock_code} 多头组合失败: {e}", exc_info=True)
        return 0


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始批量计算历史多头组合")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    try:
        # 初始化
        repository = DailyChanceRepositoryImpl()
        
        # 获取所有股票
        stocks = get_all_stocks()
        logger.info(f"共找到 {len(stocks)} 只股票")
        
        # 统计信息
        total_updated = 0
        success_count = 0
        failed_stocks = []
        
        # 处理每只股票
        for i, stock in enumerate(stocks, 1):
            logger.info(f"\n[{i}/{len(stocks)}] 处理股票: {stock['code']} ({stock['name']})")
            
            try:
                updated = calculate_stock_bullish_patterns(
                    stock_code=stock['code'],
                    stock_name=stock['name'],
                    table_name=stock['table'],
                    repository=repository
                )
                
                if updated > 0:
                    total_updated += updated
                    success_count += 1
                else:
                    logger.warning(f"股票 {stock['code']} 没有更新任何记录")
                    
            except Exception as e:
                logger.error(f"处理股票 {stock['code']} 失败: {e}", exc_info=True)
                failed_stocks.append(stock['code'])
        
        # 输出结果
        logger.info("\n" + "=" * 60)
        logger.info("批量计算完成")
        logger.info(f"总股票数: {len(stocks)}")
        logger.info(f"成功处理: {success_count} 只")
        logger.info(f"失败: {len(failed_stocks)} 只")
        logger.info(f"总更新记录数: {total_updated}")
        
        if failed_stocks:
            logger.warning(f"失败的股票: {', '.join(failed_stocks)}")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"批量计算失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

