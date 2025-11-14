"""测试急跌抢反弹插件"""
import sys
sys.path.append('..')

from datetime import datetime
from domain.services.c_point_plugin_service import CPointPluginService

def test_sharp_drop_rebound():
    """测试急跌抢反弹插件"""
    
    print("=" * 70)
    print("急跌抢反弹插件测试")
    print("=" * 70)
    
    # 创建插件服务
    plugin_service = CPointPluginService()
    
    # 测试用例
    test_cases = [
        {
            "name": "测试1: 主板连续4日急跌-21%",
            "stock_code": "SH600000",
            "date": "2024-11-14",
            "description": "应触发插件（累计跌幅达到主板-20%阈值）"
        },
        {
            "name": "测试2: 非主板连续4日急跌-26%",
            "stock_code": "SZ300001",
            "date": "2024-11-14",
            "description": "应触发插件（累计跌幅达到非主板-25%阈值）"
        },
        {
            "name": "测试3: 主板连续5日阴线-22%",
            "stock_code": "SH600001",
            "date": "2024-11-14",
            "description": "应触发插件（连续阴线且累计跌幅达标）"
        },
        {
            "name": "测试4: 跌幅不足",
            "stock_code": "SH600002",
            "date": "2024-11-14",
            "description": "不应触发插件（累计跌幅未达到阈值）"
        }
    ]
    
    print("\n注意：此测试脚本需要数据库中有实际数据才能运行")
    print("请根据实际情况修改测试用例中的股票代码和日期\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'-' * 70}")
        print(f"{test_case['name']}")
        print(f"股票代码: {test_case['stock_code']}")
        print(f"日期: {test_case['date']}")
        print(f"预期: {test_case['description']}")
        print(f"{'-' * 70}")
        
        try:
            # 初始化缓存（实际测试时需要）
            # plugin_service.init_cache(test_case['stock_code'], '2024-10-01', '2024-11-14')
            
            # 调用插件检查
            date_obj = datetime.strptime(test_case['date'], '%Y-%m-%d')
            result = plugin_service._check_sharp_drop_rebound(
                test_case['stock_code'], 
                date_obj
            )
            
            # 输出结果
            print(f"\n结果:")
            print(f"  触发状态: {'✅ 触发' if result.triggered else '❌ 未触发'}")
            print(f"  插件名称: {result.plugin_name}")
            print(f"  分数调整: {result.score_adjustment:+d}分")
            if result.reason:
                print(f"  触发原因: {result.reason}")
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)

def test_calculation_logic():
    """测试计算逻辑"""
    print("\n" + "=" * 70)
    print("计算逻辑测试")
    print("=" * 70)
    
    # 测试十字星判断
    print("\n1. 十字星判断:")
    test_klines = [
        {"open": 10.0, "close": 10.05, "expected": True},   # 实体占比0.5%
        {"open": 10.0, "close": 10.15, "expected": False},  # 实体占比1.5%
        {"open": 10.0, "close": 10.0, "expected": True},    # 实体占比0%
    ]
    
    for kline in test_klines:
        body = abs(kline['close'] - kline['open'])
        body_ratio = (body / kline['close'] * 100) if kline['close'] else 0
        is_doji = body_ratio < 1
        status = "✅" if is_doji == kline['expected'] else "❌"
        print(f"  {status} 开:{kline['open']:.2f}, 收:{kline['close']:.2f}, "
              f"实体占比:{body_ratio:.2f}%, 十字星:{is_doji}")
    
    # 测试成交量萎缩判断
    print("\n2. 成交量萎缩判断:")
    first_volume = 1000  # 第一日成交量
    test_volumes = [
        {"volume": 200, "expected": True},   # 20%
        {"volume": 150, "expected": True},   # 15%
        {"volume": 250, "expected": False},  # 25%
    ]
    
    for vol in test_volumes:
        shrink_ratio = vol['volume'] / first_volume
        is_shrink = shrink_ratio <= 0.2
        status = "✅" if is_shrink == vol['expected'] else "❌"
        print(f"  {status} 成交量:{vol['volume']}, 萎缩比例:{shrink_ratio*100:.1f}%, "
              f"极度萎缩:{is_shrink}")
    
    # 测试累计跌幅判断
    print("\n3. 累计跌幅判断:")
    test_drops = [
        {"pcts": [-5, -6, -4, -6], "board": "主板", "threshold": -20, "expected": True},   # -21%
        {"pcts": [-4, -5, -3, -4], "board": "主板", "threshold": -20, "expected": False},  # -16%
        {"pcts": [-6, -7, -5, -8], "board": "非主板", "threshold": -25, "expected": True},  # -26%
    ]
    
    for drop in test_drops:
        cum = sum(drop['pcts'])
        is_drop = cum < drop['threshold']
        status = "✅" if is_drop == drop['expected'] else "❌"
        print(f"  {status} {drop['board']}: 涨跌幅{drop['pcts']}, 累计:{cum:.1f}%, "
              f"阈值:{drop['threshold']}%, 达标:{is_drop}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    print("\n请选择测试类型：")
    print("1. 完整测试（需要数据库连接和实际数据）")
    print("2. 计算逻辑测试（无需数据库）")
    print("3. 全部测试")
    
    choice = input("\n请输入选项 (1/2/3，默认2): ").strip() or "2"
    
    if choice == "1":
        test_sharp_drop_rebound()
    elif choice == "2":
        test_calculation_logic()
    elif choice == "3":
        test_calculation_logic()
        test_sharp_drop_rebound()
    else:
        print("无效选项，执行计算逻辑测试")
        test_calculation_logic()

