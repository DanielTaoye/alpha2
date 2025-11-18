"""测试单个日期的R点检测"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def test_single_day(stock_code: str, date_str: str):
    """测试单个日期的R点"""
    print("="*100)
    print(f"测试单个日期R点: {stock_code} {date_str}")
    print("="*100)
    
    test_date = datetime.strptime(date_str, '%Y-%m-%d')
    
    # 初始化R点服务
    r_service = RPointPluginService()
    
    # 往前取30天数据
    start_date = (test_date - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = date_str
    
    print(f"初始化缓存: {start_date} 至 {end_date}")
    r_service.init_cache(stock_code, start_date, end_date)
    
    print(f"缓存数据: daily={len(r_service._daily_cache)}条, daily_chance={len(r_service._daily_chance_cache)}条\n")
    
    # 检查当日缓存数据
    if date_str in r_service._daily_cache:
        daily = r_service._daily_cache[date_str]
        print(f"当日K线数据:")
        print(f"  日期: {daily.date}")
        print(f"  开盘: {daily.open}, 收盘: {daily.close}")
        print(f"  最高: {daily.high}, 最低: {daily.low}")
        print(f"  昨收: {daily.pre_close}")
    else:
        print(f"警告: 缓存中无当日K线数据")
    
    if date_str in r_service._daily_chance_cache:
        chance = r_service._daily_chance_cache[date_str]
        print(f"\n当日daily_chance数据:")
        print(f"  volume_type: {chance.volume_type}")
        print(f"  bearish_pattern: {chance.bearish_pattern}")
        print(f"  day_win_ratio_score: {chance.day_win_ratio_score}")
    else:
        print(f"\n警告: 缓存中无当日daily_chance数据")
    
    # 执行R点检测
    print("\n" + "-"*100)
    print("执行R点检测...")
    print("-"*100)
    
    is_r_point, r_plugins = r_service.check_r_point(stock_code, test_date)
    
    print("\n" + "="*100)
    if is_r_point:
        print(f"[OK] 触发R点！")
        for plugin in r_plugins:
            print(f"\n  插件: {plugin.plugin_name}")
            print(f"  原因: {plugin.reason}")
    else:
        print(f"[NO] 未触发R点")
    print("="*100)
    
    r_service.clear_cache()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python test_single_day_r_point.py <股票代码> <日期>")
        print("示例: python test_single_day_r_point.py SZ300564 2025-07-24")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    date_str = sys.argv[2]
    test_single_day(stock_code, date_str)

