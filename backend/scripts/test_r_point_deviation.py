"""测试R点-乖离率偏离插件"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.logging.logger import get_logger
import logging

# 设置日志级别为DEBUG以查看详细日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = get_logger(__name__)


def test_r_point_deviation(stock_code: str, test_date_str: str):
    """
    测试指定股票在指定日期的R点-乖离率偏离检测
    
    Args:
        stock_code: 股票代码
        test_date_str: 测试日期，格式：YYYY-MM-DD
    """
    logger.info("="*80)
    logger.info(f"开始测试R点-乖离率偏离: {stock_code} {test_date_str}")
    logger.info("="*80)
    
    try:
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d')
        
        # 初始化R点服务
        r_service = RPointPluginService()
        
        # 初始化缓存（取前30天的数据）
        start_date = (test_date - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = test_date.strftime('%Y-%m-%d')
        logger.info(f"初始化缓存: {start_date} 至 {end_date}")
        r_service.init_cache(stock_code, start_date, end_date)
        
        logger.info(f"缓存已初始化: daily={len(r_service._daily_cache)}条, daily_chance={len(r_service._daily_chance_cache)}条")
        
        # 检查缓存中的数据
        if test_date_str in r_service._daily_cache:
            daily = r_service._daily_cache[test_date_str]
            logger.info(f"当日K线数据: close={daily.close}, high={daily.high}, low={daily.low}, volume={daily.volume}")
        else:
            logger.warning(f"缓存中无当日K线数据")
        
        if test_date_str in r_service._daily_chance_cache:
            chance = r_service._daily_chance_cache[test_date_str]
            logger.info(f"当日daily_chance数据: volume_type={chance.volume_type}, bearish_pattern={chance.bearish_pattern}")
        else:
            logger.warning(f"缓存中无当日daily_chance数据")
        
        # 执行R点检查
        logger.info("-"*80)
        logger.info("开始执行R点检测...")
        logger.info("-"*80)
        is_r_point, r_plugins = r_service.check_r_point(stock_code, test_date)
        
        # 输出结果
        logger.info("="*80)
        if is_r_point:
            logger.info(f"✓ 触发R点！")
            for plugin in r_plugins:
                logger.info(f"  插件: {plugin.plugin_name}")
                logger.info(f"  原因: {plugin.reason}")
        else:
            logger.info(f"✗ 未触发R点")
        logger.info("="*80)
        
        # 清空缓存
        r_service.clear_cache()
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python test_r_point_deviation.py <股票代码> <日期>")
        print("示例: python test_r_point_deviation.py SH600000 2024-01-15")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    test_date = sys.argv[2]
    
    test_r_point_deviation(stock_code, test_date)

