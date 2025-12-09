#!/usr/bin/env python3
"""
最终检查中集车辆2024-10-08的乖离率偏离条件
"""

import sys
sys.path.insert(0, 'backend')

from domain.services.r_point_plugin_service import RPointPluginService

service = RPointPluginService()
stock_code = 'SZ301039'
test_date = '2024-10-08'

# 获取数据
current_data = service.daily_repo.find_by_date(stock_code, test_date)
current_chance = service.daily_chance_repo.find_by_stock_and_date(stock_code, test_date)

if not current_data:
    print("❌ 未找到K线数据")
    exit()

print("=" * 80)
print("中集车辆(SZ301039) 2024-10-08 最终检查")
print("=" * 80)

# K线数据
print("K线数据:")
print(f"  开盘价: {current_data.open:.2f}")
print(f"  最高价: {current_data.high:.2f}")
print(f"  最低价: {current_data.low:.2f}")
print(f"  收盘价: {current_data.close:.2f}")
print(f"  前收价(数据库): {current_data.pre_close:.2f}")

# 获取真实的前收价
prev_dates = service._get_previous_trading_dates_from_cache(test_date)
if prev_dates:
    prev_date = prev_dates[0]
    prev_data = service.daily_repo.find_by_date(stock_code, prev_date)
    if prev_data:
        print(f"  前收价(真实): {prev_data.close:.2f} (来自{prev_date})")
        real_prev_close = prev_data.close
    else:
        print("  前收价(真实): 无法获取")
        real_prev_close = 0
else:
    print("  前收价(真实): 无法获取")
    real_prev_close = 0

# 计算振幅
if real_prev_close > 0:
    amplitude = ((current_data.high - current_data.low) / real_prev_close) * 100
    print(f"  振幅: {amplitude:.2f}%")
else:
    amplitude = 0
    print("  振幅: 无法计算")

# 检查空头K线形态
is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
threshold = 6.0 if is_main_board else 8.0
print(f"  股票类型: {'主板' if is_main_board else '非主板'}")
print(f"  振幅阈值: {threshold}%")
print(f"  振幅是否足够: {amplitude >= threshold}")

# 检查K线形态
matched_patterns = service._check_bearish_kline_patterns(current_data, stock_code)
print(f"  空头K线形态: {matched_patterns if matched_patterns else '无'}")

# 检查成交量和空头组合
if current_chance:
    volume_type = current_chance.volume_type or ""
    is_volume_xyh = service._check_volume_type(current_chance, ['X', 'Y', 'H'])
    has_bearish_pattern = service._check_bearish_pattern(current_chance)
    
    print(f"\n成交量数据:")
    print(f"  成交量类型: {volume_type}")
    print(f"  XYH放量: {is_volume_xyh}")
    print(f"  空头组合: {current_chance.bearish_pattern.strip() if has_bearish_pattern else '无'}")

# 检查涨幅条件
print(f"\n涨幅条件:")
prev_data_list = []
for prev_date in prev_dates[:20]:
    data = service.daily_repo.find_by_date(stock_code, prev_date)
    if data:
        prev_data_list.append(data)

if len(prev_data_list) >= 3:
    prev_3_day = prev_data_list[2]
    gain_3days = (current_data.close - prev_3_day.close) / prev_3_day.close * 100
    threshold_3 = 15 if is_main_board else 20
    print(f"  前3日涨幅: {gain_3days:.2f}% > {threshold_3}% : {gain_3days > threshold_3}")

if len(prev_data_list) >= 5:
    prev_5_day = prev_data_list[4]
    gain_5days = (current_data.close - prev_5_day.close) / prev_5_day.close * 100
    threshold_5 = 20 if is_main_board else 25
    print(f"  前5日涨幅: {gain_5days:.2f}% > {threshold_5}% : {gain_5days > threshold_5}")

# 最终结果
result = service._check_deviation(stock_code, test_date)
print(f"\n最终结果:")
print(f"  插件触发: {result.triggered}")
if result.triggered:
    print(f"  触发原因: {result.reason}")
else:
    print("  未触发原因: ")
    if amplitude < threshold:
        print(f"    - 振幅不足({amplitude:.2f}% < {threshold}%)")
    if not matched_patterns and not has_bearish_pattern:
        print("    - 没有空头信号（无K线形态也无组合）")
    if not is_volume_xyh:
        print("    - 成交量不满足XYH放量")

