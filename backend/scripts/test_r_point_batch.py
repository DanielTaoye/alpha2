"""批量测试R点-乖离率偏离插件"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from infrastructure.logging.logger import get_logger
import logging

# 设置日志级别
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = get_logger(__name__)


def test_r_point_batch(stock_code: str, start_date_str: str, end_date_str: str):
    """
    批量测试指定股票在一段时间内的R点检测
    
    Args:
        stock_code: 股票代码
        start_date_str: 开始日期，格式：YYYY-MM-DD
        end_date_str: 结束日期，格式：YYYY-MM-DD
    """
    logger.info("="*100)
    logger.info(f"开始批量测试R点: {stock_code} 从 {start_date_str} 到 {end_date_str}")
    logger.info("="*100)
    
    try:
        # 获取交易日数据
        daily_repo = DailyRepositoryImpl()
        daily_chance_repo = DailyChanceRepositoryImpl()
        
        # 查询该时间段的所有交易日
        logger.info(f"查询交易日数据...")
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # 往前多取30天数据以支持插件
        query_start = (start_date - timedelta(days=30)).strftime('%Y-%m-%d')
        query_end = end_date.strftime('%Y-%m-%d')
        
        daily_data_list = daily_repo.find_by_date_range(stock_code, query_start, query_end)
        logger.info(f"查询到 {len(daily_data_list)} 条日K线数据")
        
        if not daily_data_list:
            logger.error(f"未找到股票 {stock_code} 的数据")
            return
        
        # 筛选测试日期范围内的数据
        test_dates = []
        for daily in daily_data_list:
            if start_date.date() <= daily.date.date() <= end_date.date():
                test_dates.append(daily.date)
        
        logger.info(f"测试日期范围内有 {len(test_dates)} 个交易日")
        
        if not test_dates:
            logger.error(f"在指定日期范围内未找到交易日")
            return
        
        # 初始化R点服务
        r_service = RPointPluginService()
        r_service.init_cache(stock_code, query_start, query_end)
        
        logger.info(f"缓存已初始化: daily={len(r_service._daily_cache)}条, daily_chance={len(r_service._daily_chance_cache)}条")
        
        # 统计信息
        total_checked = 0
        r_point_triggered = 0
        deviation_triggered = 0
        pressure_triggered = 0
        fundamental_triggered = 0
        weak_breakout_triggered = 0
        
        r_point_dates = []
        
        # 检查daily_chance数据覆盖情况
        missing_daily_chance = []
        for test_date in test_dates:
            date_str = test_date.strftime('%Y-%m-%d')
            if date_str not in r_service._daily_chance_cache:
                missing_daily_chance.append(date_str)
        
        if missing_daily_chance:
            logger.warning(f"⚠️  缺少daily_chance数据的日期: {len(missing_daily_chance)}个")
            if len(missing_daily_chance) <= 10:
                for date_str in missing_daily_chance:
                    logger.warning(f"  - {date_str}")
            else:
                logger.warning(f"  - {missing_daily_chance[:5]} ... (共{len(missing_daily_chance)}个)")
        
        # 批量检测
        logger.info("-"*100)
        logger.info("开始批量检测R点...")
        logger.info("-"*100)
        
        last_c_date = None
        
        for test_date in test_dates:
            total_checked += 1
            date_str = test_date.strftime('%Y-%m-%d')
            
            # 检查R点
            is_r_point, r_plugins = r_service.check_r_point(stock_code, test_date, last_c_date)
            
            if is_r_point:
                r_point_triggered += 1
                plugin_names = [p.plugin_name for p in r_plugins]
                plugin_reasons = [p.reason for p in r_plugins]
                
                logger.info(f"✓ {date_str} 触发R点:")
                for plugin in r_plugins:
                    logger.info(f"    [{plugin.plugin_name}] {plugin.reason}")
                    
                    if plugin.plugin_name == "乖离率偏离":
                        deviation_triggered += 1
                    elif plugin.plugin_name == "临近压力位滞涨":
                        pressure_triggered += 1
                    elif plugin.plugin_name == "基本面突发利空":
                        fundamental_triggered += 1
                    elif plugin.plugin_name == "上冲乏力":
                        weak_breakout_triggered += 1
                
                r_point_dates.append({
                    'date': date_str,
                    'plugins': plugin_names,
                    'reasons': plugin_reasons
                })
            
            # 每处理100个交易日输出一次进度
            if total_checked % 100 == 0:
                logger.info(f"已检测 {total_checked}/{len(test_dates)} 个交易日, 触发R点: {r_point_triggered}个")
        
        # 输出统计结果
        logger.info("="*100)
        logger.info("测试完成！统计结果:")
        logger.info("="*100)
        logger.info(f"总检测交易日数: {total_checked}")
        logger.info(f"触发R点次数: {r_point_triggered} ({r_point_triggered/total_checked*100:.2f}%)")
        logger.info(f"  - 乖离率偏离: {deviation_triggered}次")
        logger.info(f"  - 临近压力位滞涨: {pressure_triggered}次")
        logger.info(f"  - 基本面突发利空: {fundamental_triggered}次")
        logger.info(f"  - 上冲乏力: {weak_breakout_triggered}次")
        logger.info(f"缺少daily_chance数据: {len(missing_daily_chance)}个交易日")
        
        if r_point_dates:
            logger.info("-"*100)
            logger.info("触发R点的日期列表:")
            for item in r_point_dates:
                logger.info(f"  {item['date']}: {', '.join(item['plugins'])}")
        
        # 清空缓存
        r_service.clear_cache()
        
    except Exception as e:
        logger.error(f"批量测试失败: {e}", exc_info=True)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python test_r_point_batch.py <股票代码> <开始日期> <结束日期>")
        print("示例: python test_r_point_batch.py SZ300564 2025-01-01 2025-11-30")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    start_date = sys.argv[2]
    end_date = sys.argv[3]
    
    test_r_point_batch(stock_code, start_date, end_date)

