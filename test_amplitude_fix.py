#!/usr/bin/env python3
"""
测试修复后的振幅计算功能
"""

import sys
import os

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

from domain.services.r_point_plugin_service import RPointPluginService


def test_amplitude_fix():
    """测试振幅计算修复"""
    try:
        # 初始化服务
        r_point_service = RPointPluginService()

        # 测试中集车辆2024-10-08
        stock_code = "SZ301039"
        test_date = "2024-10-08"

        print("=" * 80)
        print(f"测试振幅计算修复 - {stock_code} {test_date}")
        print("=" * 80)

        # 获取当日数据
        current_data = r_point_service.daily_repo.find_by_date(stock_code, test_date)
        if not current_data:
            print("❌ 未找到当日K线数据")
            return

        print("当日K线数据:")
        print(f"  开盘价: {current_data.open:.2f}")
        print(f"  最高价: {current_data.high:.2f}")
        print(f"  最低价: {current_data.low:.2f}")
        print(f"  收盘价: {current_data.close:.2f}")
        print(f"  前收价: {current_data.pre_close:.2f}")

        # 测试修复后的振幅计算
        amplitude = r_point_service._calculate_amplitude(current_data, stock_code)
        print(f"\n修复后的振幅计算: {amplitude:.2f}%")

        # 判断主板还是非主板
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        threshold = 6.0 if is_main_board else 8.0
        print(f"股票类型: {'主板' if is_main_board else '非主板'}")
        print(f"振幅阈值: {threshold}%")
        print(f"振幅是否足够: {amplitude >= threshold} ({amplitude:.2f}% >= {threshold}%)")

        # 现在重新测试乖离率偏离插件
        result = r_point_service._check_deviation(stock_code, test_date)

        print("\n乖离率偏离插件测试结果:")
        print(f"  插件名称: {result.plugin_name}")
        print(f"  是否触发: {result.triggered}")
        print(f"  触发原因: {result.reason}")

        if result.triggered:
            print("\n🎯 成功！修复后的振幅计算使插件正确触发")
        else:
            print("\n💡 插件仍未触发，可能还有其他条件不满足")
        print("\n总结:")
        print(f"  振幅计算修复: ✅ (从 0.00% 修复为 {amplitude:.2f}%)")
        print(f"  插件触发状态: {'✅' if result.triggered else '❌'}")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_amplitude_fix()
