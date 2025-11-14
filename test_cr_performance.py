"""CR点分析性能测试脚本"""
import requests
import json
import time

API_URL = "http://localhost:5000/api/cr_points/analyze"

# 测试数据（需要根据实际情况修改）
test_data = {
    "stockCode": "SH600000",  # 请修改为实际存在的股票代码
    "stockName": "测试股票",
    "tableName": "basic_data_sh600000",  # 请修改为实际的表名
    "period": "day"
}

def test_cr_analyze_performance():
    """测试CR点分析接口性能"""
    print("=" * 60)
    print("CR点分析接口性能测试")
    print("=" * 60)
    print(f"\n测试数据：")
    print(f"  股票代码: {test_data['stockCode']}")
    print(f"  表名: {test_data['tableName']}")
    print(f"  周期: {test_data['period']}")
    print("\n开始测试...\n")
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        # 发送请求
        response = requests.post(
            API_URL,
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        # 记录结束时间
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # 解析响应
        result = response.json()
        
        print("=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"\n响应时间: {elapsed_time:.2f} 秒")
        print(f"HTTP状态码: {response.status_code}")
        print(f"\n响应数据:")
        print(f"  返回码: {result.get('code')}")
        print(f"  消息: {result.get('message')}")
        
        if result.get('code') == 200:
            data = result.get('data', {})
            print(f"\nCR点统计:")
            print(f"  C点（买入点）数量: {data.get('c_points_count', 0)}")
            print(f"  R点（卖出点）数量: {data.get('r_points_count', 0)}")
            print(f"  被否决的C点数量: {data.get('rejected_c_points_count', 0)}")
            
            print("\n性能评估:")
            if elapsed_time < 3:
                print("  ✅ 优秀 (< 3秒)")
            elif elapsed_time < 5:
                print("  ✅ 良好 (3-5秒)")
            elif elapsed_time < 10:
                print("  ⚠️  可接受 (5-10秒)")
            else:
                print("  ❌ 需要优化 (> 10秒)")
        else:
            print(f"\n错误信息: {result.get('message')}")
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时（超过60秒）")
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败，请确认服务器是否启动（http://localhost:5000）")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    print("\n请注意：")
    print("1. 确保Flask服务器已启动（python backend/app.py）")
    print("2. 修改test_data中的股票代码和表名为实际存在的数据")
    print("3. 确保数据库中有对应的K线数据和daily_chance数据")
    print("\n按Enter键开始测试...")
    input()
    
    test_cr_analyze_performance()

