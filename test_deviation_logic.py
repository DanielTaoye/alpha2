#!/usr/bin/env python3
"""
测试修改后的乖离率偏离插件逻辑
验证前N日涨幅计算是否正确
"""

import sys
import os
import pymysql

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl


def test_deviation_logic():
    """测试修改后的乖离率偏离逻辑"""
    try:
        # 初始化服务
        r_point_service = RPointPluginService()

        # 测试中集车辆在2024-10-08的乖离率偏离检查
        stock_code = "SZ301039"
        test_date = "2024-10-08"

        print("=" * 80)
        print(f"测试乖离率偏离插件 - {stock_code} {test_date}")
        print("=" * 80)

        # 直接调用_check_deviation方法
        result = r_point_service._check_deviation(stock_code, test_date)

        print("\n测试结果:")
        print(f"插件名称: {result.plugin_name}")
        print(f"是否触发: {result.triggered}")
        print(f"触发原因: {result.reason}")

        print("\n✅ 测试完成")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_deviation_logic()
