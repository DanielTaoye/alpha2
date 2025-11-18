"""扫描某个时间段内触发不追涨插件的情况"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from domain.services.c_point_plugin_service import CPointPluginService

def scan_no_chase_high_range(stock_code: str, start_date: str, end_date: str):
    """扫描时间段内触发不追涨插件的情况"""
    print(f"\n{'='*100}")
    print(f"扫描【不追涨】插件触发情况")
    print(f"股票：{stock_code}")
    print(f"时间范围：{start_date} 至 {end_date}")
    print(f"{'='*100}\n")
    
    try:
        # 创建服务
        plugin_service = CPointPluginService()
        
        # 初始化缓存（往前多取15天以支持插件检查）
        start_obj = datetime.strptime(start_date, '%Y-%m-%d')
        cache_start = (start_obj - timedelta(days=15)).strftime('%Y-%m-%d')
        
        plugin_service.init_cache(stock_code, cache_start, end_date)
        
        # 获取所有日期
        daily_repo = DailyRepositoryImpl()
        klines = daily_repo.find_by_date_range(stock_code, start_date, end_date)
        
        if not klines:
            print(f"没有找到数据")
            return
        
        print(f"找到 {len(klines)} 条数据\n")
        
        # 扫描每一天
        triggered_dates = []
        
        for kline in klines:
            date_obj = kline.date if isinstance(kline.date, datetime) else datetime.strptime(kline.date, '%Y-%m-%d')
            
            # 检查不追涨插件
            plugin4_result = plugin_service._check_no_chase_high(stock_code, date_obj)
            
            if plugin4_result.triggered:
                triggered_dates.append({
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'reason': plugin4_result.reason,
                    'score_adjustment': plugin4_result.score_adjustment,
                    'close': kline.close
                })
        
        # 清空缓存
        plugin_service.clear_cache()
        
        # 输出结果
        print(f"{'='*100}")
        print(f"扫描结果：")
        print(f"{'='*100}\n")
        
        if triggered_dates:
            print(f"共触发 {len(triggered_dates)} 次【不追涨】插件\n")
            print(f"{'日期':<15} {'收盘价':<10} {'扣分':<10} {'触发原因':<70}")
            print("-" * 100)
            
            for record in triggered_dates:
                print(f"{record['date']:<15} {record['close']:<10.2f} {record['score_adjustment']:<10} {record['reason']:<70}")
        else:
            print(f"该股票在 {start_date} 至 {end_date} 期间未触发【不追涨】插件")
        
        print(f"\n{'='*100}")
        
    except Exception as e:
        print(f"\n扫描失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='扫描不追涨插件触发情况')
    parser.add_argument('stock', type=str, help='股票代码，如 SH600037')
    parser.add_argument('--start', type=str, default='2024-11-01', help='开始日期，格式：2024-11-01')
    parser.add_argument('--end', type=str, default='2025-11-18', help='结束日期，格式：2025-11-18')
    
    args = parser.parse_args()
    
    scan_no_chase_high_range(args.stock, args.start, args.end)

