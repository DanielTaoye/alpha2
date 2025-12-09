#!/usr/bin/env python3
import sys
sys.path.insert(0, 'backend')

from domain.services.r_point_plugin_service import RPointPluginService

service = RPointPluginService()
stock_code = 'SZ301039'
test_date = '2024-10-08'

# 获取数据
current_data = service.daily_repo.find_by_date(stock_code, test_date)
prev_dates = service._get_previous_trading_dates_from_cache(test_date, stock_code)
prev_data = service.daily_repo.find_by_date(stock_code, prev_dates[0])

O = current_data.open
C = current_data.close
prev_close = prev_data.close

print("=" * 80)
print(f"阴线跌幅>3% 检查")
print("=" * 80)
print(f"前收价: {prev_close:.2f}")
print(f"开盘价: {O:.2f}")
print(f"收盘价: {C:.2f}")
print()

# 计算相对开盘价的跌幅
if O > 0:
    change_from_open = ((C - O) / O) * 100
    print(f"相对开盘价跌幅: {change_from_open:.2f}%")
    print(f"是否为阴线(开>收): {O > C}")
    print(f"跌幅是否>3%: {abs(change_from_open) > 3}")
    
# 测试方法
result = service._check_bearish_line_3pct_new(O, C, prev_close)
print(f"\n方法返回结果: {result}")

# 检查完整的K线形态
matched_patterns = service._check_bearish_kline_patterns(current_data, stock_code)
print(f"\n匹配的空头K线形态: {matched_patterns if matched_patterns else '无'}")

# 检查乖离率偏离插件
plugin_result = service._check_deviation(stock_code, test_date)
print(f"\n乖离率偏离插件触发: {plugin_result.triggered}")
if plugin_result.triggered:
    print(f"触发原因: {plugin_result.reason}")

