"""测试流式微批服务"""
import sys
import os
import time
import requests

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

API_BASE_URL = "http://localhost:5000/api"


def test_streaming_service():
    """测试流式微批服务"""
    print("=" * 60)
    print("流式微批服务测试")
    print("=" * 60)
    print()
    
    # 1. 检查服务状态
    print("[测试1] 检查流式服务状态...")
    try:
        response = requests.get(f"{API_BASE_URL}/streaming/status")
        result = response.json()
        
        if result.get('code') == 200:
            data = result.get('data', {})
            is_running = data.get('is_running')
            stats = data.get('stats', {})
            
            print(f"✅ 服务状态: {'运行中' if is_running else '未运行'}")
            print(f"   总轮数: {stats.get('total_rounds', 0)}")
            print(f"   已处理: {stats.get('total_processed', 0)} 只")
            print(f"   当前批次: {stats.get('current_batch', 0)}")
            print(f"   高分股票: {stats.get('high_score_count', 0)} 只")
            print(f"   最后更新: {stats.get('last_round_time', 'N/A')}")
        else:
            print(f"❌ 获取状态失败: {result.get('message')}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        print("💡 提示：请确保Flask服务已启动")
        return False
    
    print()
    
    # 2. 查询高分股票（测试查询速度）
    print("[测试2] 查询高分股票列表（测试查询速度）...")
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{API_BASE_URL}/streaming/high_score",
            json={"limit": 100}
        )
        
        query_time = (time.time() - start_time) * 1000  # 转换为毫秒
        result = response.json()
        
        if result.get('code') == 200:
            data = result.get('data', {})
            stocks = data.get('stocks', [])
            
            print(f"✅ 查询成功！")
            print(f"   查询耗时: {query_time:.0f} ms ⚡")
            print(f"   高分股票: {len(stocks)} 只")
            print(f"   策略1阈值: {data.get('thresholds', {}).get('strategy1', 0)}")
            print(f"   策略2阈值: {data.get('thresholds', {}).get('strategy2', 0)}")
            
            # 显示前5名
            if stocks:
                print()
                print("   前5名:")
                for i, stock in enumerate(stocks[:5], 1):
                    print(f"   {i}. {stock['stock_code']} {stock['stock_name']} | "
                          f"总分:{stock['total_score']:.1f} "
                          f"(策略1:{stock['strategy1_score']:.1f}, "
                          f"策略2:{stock['strategy2_score']:.1f})")
        else:
            print(f"❌ 查询失败: {result.get('message')}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False
    
    print()
    
    # 3. 等待一段时间，观察数据更新
    print("[测试3] 等待10秒，观察数据是否更新...")
    time.sleep(10)
    
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_BASE_URL}/streaming/high_score",
            json={"limit": 100}
        )
        query_time = (time.time() - start_time) * 1000
        result = response.json()
        
        if result.get('code') == 200:
            data = result.get('data', {})
            stocks = data.get('stocks', [])
            stats = data.get('service_stats', {})
            
            print(f"✅ 再次查询成功！")
            print(f"   查询耗时: {query_time:.0f} ms ⚡")
            print(f"   高分股票: {len(stocks)} 只")
            print(f"   服务轮数: {stats.get('total_rounds', 0)} 轮")
            print(f"   已处理: {stats.get('total_processed', 0)} 只")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False
    
    print()
    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    print()
    print("💡 接下来：")
    print("   1. 访问: http://localhost:5000/high_score.html")
    print("   2. 每分钟自动刷新，查询速度 < 100ms")
    print("   3. 后台流式服务持续更新数据")
    print()
    
    return True


if __name__ == '__main__':
    success = test_streaming_service()
    sys.exit(0 if success else 1)
