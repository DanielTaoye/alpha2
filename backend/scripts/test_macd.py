"""测试MACD计算"""
import sys
import os

# 添加backend目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from domain.services.macd_service import MACDService

def test_macd_calculation():
    """测试MACD计算"""
    print("=== 测试MACD计算 ===\n")
    
    # 模拟收盘价数据（50个数据点，足够计算完整的MACD）
    close_prices = [
        10.0, 10.5, 10.3, 10.8, 11.0, 11.2, 10.9, 11.3, 11.5, 11.8,
        12.0, 11.7, 11.9, 12.2, 12.5, 12.3, 12.8, 13.0, 12.7, 13.2,
        13.5, 13.3, 13.8, 14.0, 13.7, 14.2, 14.5, 14.3, 14.8, 15.0,
        15.2, 14.9, 15.3, 15.6, 15.4, 15.9, 16.1, 15.8, 16.3, 16.5,
        16.2, 16.7, 17.0, 16.8, 17.2, 17.5, 17.3, 17.8, 18.0, 17.7
    ]
    
    print(f"收盘价数据: {len(close_prices)}个")
    print(f"收盘价范围: {min(close_prices)} - {max(close_prices)}\n")
    
    # 计算MACD
    macd_data = MACDService.calculate_macd(close_prices)
    
    print("MACD计算结果:")
    print(f"- DIF数据点: {len(macd_data['dif'])}")
    print(f"- DEA数据点: {len(macd_data['dea'])}")
    print(f"- MACD数据点: {len(macd_data['macd'])}\n")
    
    # 统计有效数据数量
    valid_dif = sum(1 for x in macd_data['dif'] if x is not None)
    valid_dea = sum(1 for x in macd_data['dea'] if x is not None)
    valid_macd = sum(1 for x in macd_data['macd'] if x is not None)
    print(f"有效数据数量: DIF={valid_dif}, DEA={valid_dea}, MACD={valid_macd}\n")
    
    # 显示最后10个有效数据
    print("最后10个MACD值:")
    for i in range(len(close_prices) - 10, len(close_prices)):
        dif = macd_data['dif'][i]
        dea = macd_data['dea'][i]
        macd = macd_data['macd'][i]
        
        dif_str = f"{dif:.4f}" if dif is not None else "None"
        dea_str = f"{dea:.4f}" if dea is not None else "None"
        macd_str = f"{macd:.4f}" if macd is not None else "None"
        
        print(f"Day {i+1}: Close={close_prices[i]:.2f}, DIF={dif_str}, DEA={dea_str}, MACD={macd_str}")
    
    print("\n[OK] MACD计算测试完成!")

if __name__ == '__main__':
    test_macd_calculation()

