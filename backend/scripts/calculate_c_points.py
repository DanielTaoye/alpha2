"""
批量计算所有股票的C点
基于新的策略一：赔率分 + 胜率分
"""
import sys
import os
from datetime import datetime, timedelta
from typing import List

# 添加项目根目录到Python路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from infrastructure.persistence.daily_data_repository_impl import DailyDataRepositoryImpl
from application.services.cr_point_service import CRPointService
from domain.models.kline import KLineData

logger = get_logger(__name__)


def get_all_stock_codes() -> List[str]:
    """获取所有股票代码"""
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            sql = "SELECT DISTINCT stock_code FROM daily_chance ORDER BY stock_code"
            cursor.execute(sql)
            results = cursor.fetchall()
            return [row['stock_code'] for row in results]
    except Exception as e:
        logger.error(f"获取股票代码失败: {e}", exc_info=True)
        return []


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始批量计算所有股票的C点")
    logger.info(f"执行时间: {datetime.now()}")
    logger.info("=" * 60)
    
    # 初始化服务
    cr_service = CRPointService()
    daily_data_repo = DailyDataRepositoryImpl()
    
    # 获取所有股票代码
    stock_codes = get_all_stock_codes()
    logger.info(f"找到 {len(stock_codes)} 只股票")
    
    # 统计信息
    total_stocks = len(stock_codes)
    success_count = 0
    fail_count = 0
    total_c_points = 0
    
    # 计算日期范围（最近450个交易日）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=600)  # 多取一些天数确保有450个交易日
    
    # 逐个股票处理
    for idx, stock_code in enumerate(stock_codes, 1):
        try:
            logger.info(f"\n[{idx}/{total_stocks}] 处理股票: {stock_code}")
            
            # 获取日线数据
            daily_data_list = daily_data_repo.find_by_date_range(
                stock_code, 
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            
            if not daily_data_list:
                logger.warning(f"股票 {stock_code} 没有日线数据")
                continue
            
            # 转换为KLineData格式
            kline_data = []
            for data in daily_data_list:
                kline = KLineData(
                    time=data.date,
                    open=data.open,
                    high=data.high,
                    low=data.low,
                    close=data.close,
                    volume=data.volume
                )
                kline_data.append(kline)
            
            logger.info(f"股票 {stock_code} 有 {len(kline_data)} 条日线数据")
            
            # 分析并保存C点
            result = cr_service.analyze_and_save_cr_points(
                stock_code=stock_code,
                stock_name='',  # 股票名称可以从daily_chance中获取，这里暂时为空
                kline_data=kline_data
            )
            
            c_points_count = result['c_points_count']
            total_c_points += c_points_count
            
            if c_points_count > 0:
                logger.info(f"股票 {stock_code} 成功计算 {c_points_count} 个C点")
            else:
                logger.warning(f"股票 {stock_code} 没有找到C点")
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"处理股票 {stock_code} 失败: {e}", exc_info=True)
            fail_count += 1
            continue
    
    # 输出统计结果
    logger.info("\n" + "=" * 60)
    logger.info("批量计算完成！")
    logger.info(f"总股票数: {total_stocks}")
    logger.info(f"成功处理: {success_count} 只")
    logger.info(f"失败: {fail_count} 只")
    logger.info(f"总C点数: {total_c_points}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

