"""快速扫描触发急跌抢反弹插件的股票（仅检查最近一天）"""
import sys
sys.path.append('..')

from datetime import datetime, timedelta
from domain.models.stock import StockGroups
from domain.services.c_point_plugin_service import CPointPluginService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def quick_scan():
    """快速扫描所有股票，仅检查最近一天"""
    
    print("=" * 80)
    print("快速扫描触发【急跌抢反弹】插件的股票（仅检查最近一天）")
    print("=" * 80)
    
    # 获取所有股票
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    # 统计
    total_stocks = 0
    triggered_stocks = []
    error_stocks = []
    
    # 创建插件服务
    plugin_service = CPointPluginService()
    
    # 检查日期：今天
    check_date = datetime.now()
    # 缓存需要往前15天的数据
    cache_start_date = check_date - timedelta(days=15)
    
    print(f"\n检查日期: {check_date.strftime('%Y-%m-%d')}")
    print(f"数据范围: {cache_start_date.strftime('%Y-%m-%d')} 至 {check_date.strftime('%Y-%m-%d')}")
    print(f"\n开始扫描...\n")
    
    # 遍历所有分组
    for group_name, stocks in all_groups.items():
        print(f"[{group_name}]", end=" ")
        
        for stock in stocks:
            total_stocks += 1
            stock_code = stock.code
            stock_name = stock.name
            
            # 简单进度显示
            print(".", end="", flush=True)
            
            try:
                # 初始化缓存
                plugin_service.init_cache(
                    stock_code, 
                    cache_start_date.strftime('%Y-%m-%d'),
                    check_date.strftime('%Y-%m-%d')
                )
                
                # 调用插件检查
                result = plugin_service._check_sharp_drop_rebound(stock_code, check_date)
                
                # 清空缓存
                plugin_service.clear_cache()
                
                if result.triggered:
                    triggered_stocks.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'group': group_name,
                        'date': check_date.strftime('%Y-%m-%d'),
                        'reason': result.reason,
                        'score': result.score_adjustment
                    })
                    print(f"✅", end="", flush=True)
                    
            except Exception as e:
                error_stocks.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'error': str(e)
                })
                print("❌", end="", flush=True)
        
        print()  # 换行
    
    # 输出汇总报告
    print("\n" + "=" * 80)
    print("扫描完成 - 汇总报告")
    print("=" * 80)
    
    print(f"\n总计扫描: {total_stocks}只股票")
    print(f"触发插件: {len(triggered_stocks)}只股票")
    print(f"扫描失败: {len(error_stocks)}只股票")
    
    # 详细输出触发的股票
    if triggered_stocks:
        print("\n" + "=" * 80)
        print("🎯 触发【急跌抢反弹】插件的股票")
        print("=" * 80)
        
        for i, info in enumerate(triggered_stocks, 1):
            print(f"\n{i}. {info['stock_name']}({info['stock_code']}) [{info['group']}]")
            print(f"   触发日期: {info['date']}")
            print(f"   触发原因: {info['reason']}")
            
        # 输出简洁列表
        print("\n" + "-" * 80)
        print("简洁列表（便于复制）：")
        print("-" * 80)
        for info in triggered_stocks:
            print(f"{info['stock_name']}({info['stock_code']})")
    else:
        print("\n未发现触发插件的股票")
    
    # 输出失败的股票（如果较少）
    if error_stocks and len(error_stocks) <= 10:
        print("\n" + "=" * 80)
        print("扫描失败的股票")
        print("=" * 80)
        
        for i, info in enumerate(error_stocks, 1):
            print(f"{i}. {info['stock_name']}({info['stock_code']})")
            print(f"   错误: {info['error']}")
    elif error_stocks:
        print(f"\n注意: 有{len(error_stocks)}只股票扫描失败（可能是数据不足）")
    
    print("\n" + "=" * 80)
    
    return triggered_stocks


if __name__ == "__main__":
    try:
        triggered = quick_scan()
        
        if triggered:
            print(f"\n✅ 找到 {len(triggered)} 只触发急跌抢反弹的股票！")
        else:
            print("\n提示: 如果没有找到触发的股票，可能是因为：")
            print("  1. 最近没有股票满足急跌抢反弹条件")
            print("  2. 数据库中缺少相关数据（daily_chance表）")
            print("  3. 可以尝试扫描更多天数（使用scan_sharp_drop_rebound.py）")
            
    except KeyboardInterrupt:
        print("\n\n用户中断扫描")
    except Exception as e:
        print(f"\n\n❌ 扫描失败: {e}")
        import traceback
        traceback.print_exc()

