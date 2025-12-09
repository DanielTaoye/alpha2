#!/usr/bin/env python3
"""
检查中集车辆2024-10-08的成交量和空头信号条件
"""

import sys
import os
import pymysql

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

from domain.services.r_point_plugin_service import RPointPluginService


def check_volume_and_signals():
    """检查成交量和空头信号条件"""
    try:
        # 初始化服务
        r_point_service = RPointPluginService()

        # 测试中集车辆2024-10-08
        stock_code = "SZ301039"
        test_date = "2024-10-08"

        print("=" * 80)
        print(f"检查中集车辆({stock_code}) 2024-10-08的成交量和信号条件")
        print("=" * 80)

        # 获取当日数据
        current_data = r_point_service.daily_repo.find_by_date(stock_code, test_date)
        if not current_data:
            print("❌ 未找到当日K线数据")
            return

        # 获取当日daily_chance数据
        current_chance = r_point_service.daily_chance_repo.find_by_stock_and_date(stock_code, test_date)

        print("\n当日K线数据:")
        print(f"开盘价: {current_data.open:.2f}")
        print(f"最高价: {current_data.high:.2f}")
        print(f"最低价: {current_data.low:.2f}")
        print(f"收盘价: {current_data.close:.2f}")
        print(f"前收价: {current_data.pre_close:.2f}")

        # 计算振幅
        amplitude = 0
        if current_data.pre_close and current_data.pre_close > 0:
            amplitude = ((current_data.high - current_data.low) / current_data.pre_close) * 100
        print(f"振幅: {amplitude:.2f}%")

        # 判断主板还是非主板
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        print(f"主板股票: {is_main_board}")

        # 振幅阈值
        amplitude_threshold = 6.0 if is_main_board else 8.0
        print(f"振幅阈值: {amplitude_threshold}%")
        print(f"振幅是否足够: {amplitude > amplitude_threshold}")

        print("\n成交量数据:")
        if current_chance:
            volume_type = current_chance.volume_type or ""
            print(f"成交量类型: {volume_type}")

            # 检查XYH放量条件
            is_volume_xyh = r_point_service._check_volume_type(current_chance, ['X', 'Y', 'H'])
            print(f"XYH放量: {is_volume_xyh}")

            # 检查XYZH超放量条件
            is_volume_xyzh = r_point_service._check_volume_type(current_chance, ['X', 'Y', 'Z', 'H'])
            print(f"XYZH超放量: {is_volume_xyzh}")

            # 检查空头组合
            has_bearish_pattern = r_point_service._check_bearish_pattern(current_chance)
            bearish_patterns = current_chance.bearish_pattern.strip() if current_chance.bearish_pattern else ""
            print(f"空头组合: {has_bearish_pattern} ({bearish_patterns})")
        else:
            print("❌ 无daily_chance数据")
            return

        print("\n空头K线检查:")
        # 检查空头K线形态
        matched_patterns = r_point_service._check_bearish_kline_patterns(current_data, stock_code)
        is_bearish_kline = len(matched_patterns) > 0
        print(f"空头K线形态: {is_bearish_kline} ({', '.join(matched_patterns) if matched_patterns else '无'})")

        print("\n条件判断结果:")
        print(f"1. 振幅>阈值: {amplitude > amplitude_threshold} ({amplitude:.2f}% > {amplitude_threshold}%)")
        print(f"2. XYH放量: {is_volume_xyh} (成交量类型: {volume_type})")
        print(f"3. XYZH超放量: {is_volume_xyzh} (成交量类型: {volume_type})")
        print(f"4. 空头K线: {is_bearish_kline} ({', '.join(matched_patterns) if matched_patterns else '无'})")
        print(f"5. 空头组合: {has_bearish_pattern} ({bearish_patterns})")

        # 分析为什么没有触发
        print("\n❓ 为什么没有触发乖离率偏离?")
        print("前3日涨幅28.64% > 20% ✅ 满足")
        print("前5日涨幅33.88% > 25% ✅ 满足")
        print(f"振幅{amplitude:.2f}% > {amplitude_threshold}%: {'✅ 满足' if amplitude > amplitude_threshold else '❌ 不满足'}")
        print(f"XYH放量: {'✅ 满足' if is_volume_xyh else '❌ 不满足'}")
        print(f"空头K线或空头组合: {'✅ 满足' if (is_bearish_kline or has_bearish_pattern) else '❌ 不满足'}")

        if amplitude <= amplitude_threshold:
            print(f"\n🔴 主要问题：振幅{amplitude:.2f}% ≤ 阈值{amplitude_threshold}%")
        elif not is_volume_xyh:
            print(f"\n🔴 主要问题：成交量类型'{volume_type}'不包含XYH")
        elif not (is_bearish_kline or has_bearish_pattern):
            print(f"\n🔴 主要问题：没有空头K线形态也没有空头组合")

    except Exception as e:
        print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_volume_and_signals()
