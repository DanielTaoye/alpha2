#!/usr/bin/env python3
"""
详细测试中集车辆2024-10-08的所有乖离率偏离条件
"""

import sys
import os

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

from domain.services.r_point_plugin_service import RPointPluginService


def detailed_test():
    """详细测试所有条件"""
    try:
        # 初始化服务
        r_point_service = RPointPluginService()

        # 测试中集车辆2024-10-08
        stock_code = "SZ301039"
        test_date = "2024-10-08"

        print("=" * 100)
        print(f"详细测试中集车辆({stock_code}) 2024-10-08的乖离率偏离条件")
        print("=" * 100)

        # 获取数据
        current_data = r_point_service.daily_repo.find_by_date(stock_code, test_date)
        current_chance = r_point_service.daily_chance_repo.find_by_stock_and_date(stock_code, test_date)

        if not current_data:
            print("❌ 未找到K线数据")
            return

        # 基本信息
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        amplitude = r_point_service._calculate_amplitude(current_data, stock_code)
        amplitude_threshold = 6.0 if is_main_board else 8.0

        print("
📊 基本信息:"        print(f"  股票代码: {stock_code} ({'主板' if is_main_board else '非主板'})")
        print(f"  测试日期: {test_date}")
        print(f"  开盘价: {current_data.open:.2f}")
        print(f"  最高价: {current_data.high:.2f}")
        print(f"  最低价: {current_data.low:.2f}")
        print(f"  收盘价: {current_data.close:.2f}")
        print(f"  振幅: {amplitude:.2f}% (阈值: {amplitude_threshold}%)")

        if current_chance:
            volume_type = current_chance.volume_type or ""
            is_volume_xyh = r_point_service._check_volume_type(current_chance, ['X', 'Y', 'H'])
            is_volume_xyzh = r_point_service._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            has_bearish_pattern = r_point_service._check_bearish_pattern(current_chance)

            print(f"  成交量类型: {volume_type}")
            print(f"  XYH放量: {is_volume_xyh}")
            print(f"  XYZH超放量: {is_volume_xyzh}")
            print(f"  空头组合: {has_bearish_pattern}")

            if has_bearish_pattern:
                print(f"    组合详情: {current_chance.bearish_pattern.strip()}")
        else:
            print("  ❌ 无daily_chance数据")
            return

        # 检查空头K线
        matched_patterns = r_point_service._check_bearish_kline_patterns(current_data, stock_code)
        is_bearish_kline = len(matched_patterns) > 0
        print(f"  空头K线: {is_bearish_kline}")
        if matched_patterns:
            print(f"    K线形态: {', '.join(matched_patterns)}")

        print("
🔍 涨幅条件检查:"        # 获取历史数据
        prev_dates = r_point_service._get_previous_trading_dates_from_cache(test_date)
        prev_data_list = []
        for prev_date in prev_dates[:20]:
            data = r_point_service.daily_repo.find_by_date(stock_code, prev_date)
            if data:
                prev_data_list.append(data)

        # 检查各项涨幅条件
        conditions_status = []

        # 条件2: 前3日涨幅
        if len(prev_data_list) >= 3:
            prev_3_day = prev_data_list[2]
            gain_3days = (current_data.close - prev_3_day.close) / prev_3_day.close * 100
            threshold_3 = 15 if is_main_board else 20
            conditions_status.append(("前3日涨幅", gain_3days, threshold_3))

        # 条件3: 前5日涨幅
        if len(prev_data_list) >= 5:
            prev_5_day = prev_data_list[4]
            gain_5days = (current_data.close - prev_5_day.close) / prev_5_day.close * 100
            threshold_5 = 20 if is_main_board else 25
            conditions_status.append(("前5日涨幅", gain_5days, threshold_5))

        # 条件5: 前15日涨幅
        if len(prev_data_list) >= 15:
            prev_15_day = prev_data_list[14]
            gain_15days = (current_data.close - prev_15_day.close) / prev_15_day.close * 100
            conditions_status.append(("前15日涨幅", gain_15days, 50))

        # 条件6: 前20日涨幅
        if len(prev_data_list) >= 20:
            prev_20_day = prev_data_list[19]
            gain_20days = (current_data.close - prev_20_day.close) / prev_20_day.close * 100
            conditions_status.append(("前20日涨幅", gain_20days, 50))

        for condition_name, actual_value, threshold in conditions_status:
            status = "✅ 满足" if actual_value > threshold else "❌ 不满足"
            print(f"  {condition_name}: {actual_value:.2f}% > {threshold}% - {status}")

        print("
🎯 综合判断:"        print(f"  振幅条件: {'✅' if amplitude >= amplitude_threshold else '❌'} ({amplitude:.2f}% >= {amplitude_threshold}%)")
        print(f"  成交量条件: {'✅' if is_volume_xyh else '❌'} (XYH放量)")
        print(f"  空头信号: {'✅' if (is_bearish_kline or has_bearish_pattern) else '❌'} (K线或组合)")

        # 涨幅条件统计
        satisfied_gain_conditions = sum(1 for _, actual, threshold in conditions_status if actual > threshold)
        print(f"  涨幅条件: {satisfied_gain_conditions}/{len(conditions_status)} 个满足")

        # 最终判断
        gain_ok = satisfied_gain_conditions > 0
        volume_ok = is_volume_xyh
        signal_ok = is_bearish_kline or has_bearish_pattern
        amplitude_ok = amplitude >= amplitude_threshold

        should_trigger = gain_ok and volume_ok and signal_ok and amplitude_ok

        print("
📋 最终结果:"        print(f"  应该触发: {should_trigger}")
        print(f"    - 涨幅满足: {gain_ok}")
        print(f"    - 成交量满足: {volume_ok}")
        print(f"    - 信号满足: {signal_ok}")
        print(f"    - 振幅满足: {amplitude_ok}")

        if should_trigger:
            print("  🎉 插件应该触发！")
        else:
            print("  💭 插件不应该触发")
            missing = []
            if not gain_ok: missing.append("涨幅")
            if not volume_ok: missing.append("成交量")
            if not signal_ok: missing.append("空头信号")
            if not amplitude_ok: missing.append("振幅")
            print(f"  缺少条件: {', '.join(missing)}")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    detailed_test()
