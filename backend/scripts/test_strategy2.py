"""测试策略2 C点计算"""
import sys
import os

# 添加backend目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from domain.services.strategy2_service import Strategy2Service
from domain.services.ma_service import MAService
from domain.services.macd_service import MACDService
from datetime import datetime

def test_strategy2():
    """测试策略2计算"""
    print("=== 测试策略2 C点计算 ===\n")
    
    # 模拟收盘价数据（60个数据点）
    close_prices = [
        10.0, 10.2, 10.5, 10.3, 10.8, 11.0, 11.2, 10.9, 11.3, 11.5,
        11.8, 12.0, 11.7, 11.9, 12.2, 12.5, 12.3, 12.8, 13.0, 12.7,
        13.2, 13.5, 13.3, 13.8, 14.0, 13.7, 14.2, 14.5, 14.3, 14.8,
        15.0, 15.2, 14.9, 15.3, 15.6, 15.4, 15.9, 16.1, 15.8, 16.3,
        16.5, 16.2, 16.7, 17.0, 16.8, 17.2, 17.5, 17.3, 17.8, 18.0,
        17.7, 17.9, 18.2, 18.0, 18.5, 18.7, 18.4, 18.9, 19.1, 19.0
    ]
    
    print(f"收盘价数据: {len(close_prices)}个")
    print(f"收盘价范围: {min(close_prices)} - {max(close_prices)}\n")
    
    # 计算MA
    ma_data = MAService.calculate_multiple_ma(close_prices, periods=[5, 10, 20])
    print("MA计算完成")
    
    # 计算MACD
    macd_data = MACDService.calculate_macd(close_prices)
    print("MACD计算完成\n")
    
    # 准备前30个交易日数据（用于低位判断）
    daily_data_30 = []
    for i in range(30, 60):
        if i >= 29:
            for j in range(i - 29, i + 1):
                daily_data_30.append({
                    'high': close_prices[j] * 1.02,
                    'low': close_prices[j] * 0.98,
                    'close': close_prices[j]
                })
    
    # 创建策略2服务
    strategy2_service = Strategy2Service()
    
    # 测试几个典型场景
    test_cases = [
        {
            'index': 50,
            'volume_type': 'A,B',
            'bullish_pattern': '看涨吞没',
            'description': '温和放量 + 多头组合'
        },
        {
            'index': 55,
            'volume_type': 'H',
            'bullish_pattern': '早晨之星',
            'description': 'H型放量 + 多头组合'
        },
        {
            'index': 58,
            'volume_type': None,
            'bullish_pattern': None,
            'description': '无特殊信号'
        }
    ]
    
    print("测试不同场景:\n")
    for idx, test_case in enumerate(test_cases, 1):
        index = test_case['index']
        
        is_triggered, score, reason = strategy2_service.check_strategy2(
            stock_code='TEST001',
            date=datetime(2025, 1, 1),
            close_price=close_prices[index],
            ma_data=ma_data,
            macd_data=macd_data,
            volume_type=test_case['volume_type'],
            bullish_pattern=test_case['bullish_pattern'],
            daily_data_30=daily_data_30 if len(daily_data_30) >= 30 else [],
            index=index
        )
        
        print(f"场景{idx}: {test_case['description']}")
        print(f"  索引: {index}, 收盘价: {close_prices[index]:.2f}")
        print(f"  触发: {'是' if is_triggered else '否'}")
        print(f"  得分: {score:.0f}分")
        print(f"  原因: {reason}")
        print()
    
    print("[OK] 策略2测试完成!")

if __name__ == '__main__':
    test_strategy2()

