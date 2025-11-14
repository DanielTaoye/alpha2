"""测试被否决的C点"""
import sys
import os
from datetime import datetime

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from domain.services.cr_strategy_service import CRStrategyService

# 测试股票
stock_code = 'SZ002130'
test_date = datetime(2025, 10, 24)

cr_service = CRStrategyService()

print(f"测试股票: {stock_code}")
print(f"测试日期: {test_date}")
print("=" * 60)

# 调用C点检查
is_triggered, final_score, strategy, plugins, base_score, is_rejected = cr_service.check_c_point_strategy_1(
    stock_code, 
    test_date
)

print(f"\n基础分: {base_score:.2f}")
print(f"最终分: {final_score:.2f}")
print(f"是否触发C点: {is_triggered}")
print(f"是否被插件否决: {is_rejected}")
print(f"触发的插件数量: {len(plugins)}")

if plugins:
    print("\n触发的插件：")
    for plugin in plugins:
        print(f"  - {plugin['pluginName']}: {plugin['reason']}")
        print(f"    分数调整: {plugin['scoreAdjustment']}")

print("\n结论:")
if is_triggered:
    print("✅ 正常触发C点")
elif is_rejected:
    print("⚠️ 被插件否决（基础分>=70但最终分<70）")
else:
    print("❌ 未触发C点（基础分<70或最终分<70但基础分也<70）")

