"""
测试R点插件参数配置功能
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from domain.services.config_service import get_config_service


def test_r_plugin_config():
    """测试R点插件配置的读取和更新"""
    
    config_service = get_config_service()
    
    print("=" * 60)
    print("R点插件参数配置测试")
    print("=" * 60)
    
    # 1. 读取当前配置
    print("\n1. 读取当前配置:")
    print("-" * 60)
    
    pressure_distance = config_service.get_pressure_stagnation_distance_threshold()
    high_position_gain = config_service.get_high_position_gain_threshold()
    
    print(f"临近压力位滞涨 - 距离阈值: {pressure_distance}%")
    print(f"高位发R - 涨幅阈值: {high_position_gain}%")
    
    # 2. 显示完整配置
    print("\n2. 完整配置内容:")
    print("-" * 60)
    
    full_config = config_service.get_config()
    import json
    print(json.dumps(full_config, indent=2, ensure_ascii=False))
    
    # 3. 测试更新配置
    print("\n3. 测试更新配置:")
    print("-" * 60)
    
    test_pressure_distance = 12.0
    test_high_position_gain = 10.0
    
    print(f"更新临近压力位滞涨距离阈值为: {test_pressure_distance}%")
    print(f"更新高位发R涨幅阈值为: {test_high_position_gain}%")
    
    updated_config = config_service.update_config(
        pressure_distance_threshold=test_pressure_distance,
        high_position_gain_threshold=test_high_position_gain
    )
    
    print("\n更新后的配置:")
    print(json.dumps(updated_config, indent=2, ensure_ascii=False))
    
    # 4. 验证更新结果
    print("\n4. 验证更新结果:")
    print("-" * 60)
    
    new_pressure_distance = config_service.get_pressure_stagnation_distance_threshold()
    new_high_position_gain = config_service.get_high_position_gain_threshold()
    
    assert new_pressure_distance == test_pressure_distance, "临近压力位滞涨距离阈值更新失败"
    assert new_high_position_gain == test_high_position_gain, "高位发R涨幅阈值更新失败"
    
    print(f"✅ 临近压力位滞涨距离阈值验证通过: {new_pressure_distance}%")
    print(f"✅ 高位发R涨幅阈值验证通过: {new_high_position_gain}%")
    
    # 5. 恢复默认值
    print("\n5. 恢复默认值:")
    print("-" * 60)
    
    config_service.update_config(
        pressure_distance_threshold=10.0,
        high_position_gain_threshold=8.0
    )
    
    restored_pressure = config_service.get_pressure_stagnation_distance_threshold()
    restored_gain = config_service.get_high_position_gain_threshold()
    
    print(f"✅ 已恢复临近压力位滞涨距离阈值为: {restored_pressure}%")
    print(f"✅ 已恢复高位发R涨幅阈值为: {restored_gain}%")
    
    print("\n" + "=" * 60)
    print("测试完成！所有功能正常")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_r_plugin_config()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

