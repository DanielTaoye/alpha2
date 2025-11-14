"""扫描触发急跌抢反弹插件的股票"""
import sys
sys.path.append('..')

from datetime import datetime, timedelta
from domain.models.stock import StockGroups
from domain.services.c_point_plugin_service import CPointPluginService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def scan_all_stocks():
    """扫描所有股票，找出触发急跌抢反弹插件的股票"""
    
    print("=" * 80)
    print("扫描触发【急跌抢反弹】插件的股票")
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
    
    # 扫描日期范围：最近5个交易日
    end_date = datetime.now()
    start_date = end_date - timedelta(days=15)  # 往前15天确保有足够数据
    
    print(f"\n扫描日期范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    print(f"开始扫描...\n")
    
    # 遍历所有分组
    for group_name, stocks in all_groups.items():
        print(f"\n{'='*60}")
        print(f"分组: {group_name} ({len(stocks)}只股票)")
        print(f"{'='*60}")
        
        for stock in stocks:
            total_stocks += 1
            stock_code = stock.code
            stock_name = stock.name
            
            try:
                # 初始化缓存
                plugin_service.init_cache(
                    stock_code, 
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )
                
                # 检查最近5个交易日
                triggered = False
                trigger_info = None
                
                for i in range(10):  # 检查最近10天
                    check_date = end_date - timedelta(days=i)
                    
                    # 调用插件检查
                    result = plugin_service._check_sharp_drop_rebound(stock_code, check_date)
                    
                    if result.triggered:
                        triggered = True
                        trigger_info = {
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'group': group_name,
                            'date': check_date.strftime('%Y-%m-%d'),
                            'reason': result.reason,
                            'score': result.score_adjustment
                        }
                        break
                
                # 清空缓存
                plugin_service.clear_cache()
                
                if triggered:
                    triggered_stocks.append(trigger_info)
                    print(f"  ✅ {stock_name}({stock_code}) - {trigger_info['date']}")
                    print(f"      原因: {trigger_info['reason']}")
                else:
                    print(f"  ⚪ {stock_name}({stock_code}) - 未触发")
                    
            except Exception as e:
                error_stocks.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'error': str(e)
                })
                print(f"  ❌ {stock_name}({stock_code}) - 扫描失败: {e}")
    
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
        print("触发【急跌抢反弹】插件的股票详情")
        print("=" * 80)
        
        for i, info in enumerate(triggered_stocks, 1):
            print(f"\n{i}. {info['stock_name']}({info['stock_code']})")
            print(f"   分组: {info['group']}")
            print(f"   触发日期: {info['date']}")
            print(f"   触发原因: {info['reason']}")
            print(f"   分数: {info['score']}")
    else:
        print("\n未发现触发插件的股票")
    
    # 输出失败的股票
    if error_stocks:
        print("\n" + "=" * 80)
        print("扫描失败的股票")
        print("=" * 80)
        
        for i, info in enumerate(error_stocks, 1):
            print(f"{i}. {info['stock_name']}({info['stock_code']}) - {info['error']}")
    
    print("\n" + "=" * 80)
    
    return triggered_stocks


def scan_single_stock(stock_code: str, days: int = 30):
    """
    扫描单只股票最近N天的情况
    
    Args:
        stock_code: 股票代码
        days: 扫描天数
    """
    print("=" * 80)
    print(f"扫描股票: {stock_code} (最近{days}天)")
    print("=" * 80)
    
    # 获取股票信息
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    stock_name = None
    for group_name, stocks in all_groups.items():
        for stock in stocks:
            if stock.code == stock_code:
                stock_name = stock.name
                break
        if stock_name:
            break
    
    if not stock_name:
        print(f"❌ 未找到股票代码: {stock_code}")
        return
    
    print(f"\n股票名称: {stock_name}")
    print(f"股票代码: {stock_code}")
    
    # 创建插件服务
    plugin_service = CPointPluginService()
    
    # 日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days+10)
    
    try:
        # 初始化缓存
        plugin_service.init_cache(
            stock_code,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        print(f"\n逐日检查结果:")
        print("-" * 80)
        
        triggered_dates = []
        
        for i in range(days):
            check_date = end_date - timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            
            # 调用插件检查
            result = plugin_service._check_sharp_drop_rebound(stock_code, check_date)
            
            if result.triggered:
                triggered_dates.append({
                    'date': date_str,
                    'reason': result.reason,
                    'score': result.score_adjustment
                })
                print(f"✅ {date_str}: 触发插件")
                print(f"   {result.reason}")
            else:
                print(f"⚪ {date_str}: 未触发")
        
        # 清空缓存
        plugin_service.clear_cache()
        
        # 汇总
        print("\n" + "=" * 80)
        print("汇总")
        print("=" * 80)
        print(f"触发天数: {len(triggered_dates)}/{days}天")
        
        if triggered_dates:
            print("\n触发详情:")
            for info in triggered_dates:
                print(f"  - {info['date']}: {info['reason']}")
        
    except Exception as e:
        print(f"\n❌ 扫描失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='扫描触发急跌抢反弹插件的股票')
    parser.add_argument('--stock', type=str, help='扫描指定股票代码')
    parser.add_argument('--days', type=int, default=30, help='扫描天数（默认30天）')
    parser.add_argument('--all', action='store_true', help='扫描所有股票')
    
    args = parser.parse_args()
    
    if args.stock:
        # 扫描单只股票
        scan_single_stock(args.stock, args.days)
    elif args.all:
        # 扫描所有股票
        scan_all_stocks()
    else:
        # 默认扫描所有股票
        print("提示: 使用 --stock SH600000 扫描指定股票")
        print("     使用 --all 扫描所有股票")
        print("     使用 --days 30 指定扫描天数\n")
        
        choice = input("请选择:\n1. 扫描所有股票\n2. 扫描指定股票\n\n请输入选项(1/2，默认1): ").strip() or "1"
        
        if choice == "1":
            scan_all_stocks()
        elif choice == "2":
            stock_code = input("请输入股票代码(如SH600000): ").strip()
            days = input("请输入扫描天数(默认30): ").strip() or "30"
            scan_single_stock(stock_code, int(days))
        else:
            print("无效选项")

