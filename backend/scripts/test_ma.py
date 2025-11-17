"""测试移动平均线(MA)计算"""
import sys
import os

# 添加backend目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from domain.services.ma_service import MAService

def test_ma_calculation():
    """测试MA计算"""
    print("=== 测试MA计算 ===\n")
    
    # 模拟收盘价数据（30个数据点）
    close_prices = [
        10.0, 10.5, 10.3, 10.8, 11.0, 11.2, 10.9, 11.3, 11.5, 11.8,
        12.0, 11.7, 11.9, 12.2, 12.5, 12.3, 12.8, 13.0, 12.7, 13.2,
        13.5, 13.3, 13.8, 14.0, 13.7, 14.2, 14.5, 14.3, 14.8, 15.0
    ]
    
    print(f"收盘价数据: {len(close_prices)}个")
    print(f"收盘价范围: {min(close_prices)} - {max(close_prices)}\n")
    
    # 计算多条均线
    ma_data = MAService.calculate_multiple_ma(close_prices, periods=[5, 10, 20])
    
    print("MA计算结果:")
    for key, values in ma_data.items():
        valid_count = sum(1 for x in values if x is not None)
        print(f"- {key.upper()}: 数据点{len(values)}个, 有效{valid_count}个")
    
    print("\n最后10个MA值:")
    for i in range(len(close_prices) - 10, len(close_prices)):
        ma5 = ma_data['ma5'][i]
        ma10 = ma_data['ma10'][i]
        ma20 = ma_data['ma20'][i]
        
        ma5_str = f"{ma5:.2f}" if ma5 is not None else "None"
        ma10_str = f"{ma10:.2f}" if ma10 is not None else "None"
        ma20_str = f"{ma20:.2f}" if ma20 is not None else "None"
        
        print(f"Day {i+1}: Close={close_prices[i]:.2f}, MA5={ma5_str}, MA10={ma10_str}, MA20={ma20_str}")
    
    # 验证MA5计算是否正确（手动验证最后一个值）
    last_5_prices = close_prices[-5:]
    expected_ma5 = sum(last_5_prices) / 5
    actual_ma5 = ma_data['ma5'][-1]
    
    print(f"\n验证MA5最后一个值:")
    print(f"最后5个收盘价: {last_5_prices}")
    print(f"期望值: {expected_ma5:.2f}")
    print(f"实际值: {actual_ma5:.2f}")
    
    if abs(expected_ma5 - actual_ma5) < 0.01:
        print("[OK] MA5计算正确!")
    else:
        print("[ERROR] MA5计算错误!")
    
    print("\n[OK] MA计算测试完成!")

if __name__ == '__main__':
    test_ma_calculation()

