"""检查不追涨插件的触发情况"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.database import DatabaseConnection

def check_no_chase_high(stock_code: str, target_date: str):
    """检查不追涨插件在特定日期的触发情况"""
    print(f"\n{'='*100}")
    print(f"检查【不追涨】插件 - {stock_code} @ {target_date}")
    print(f"{'='*100}\n")
    
    try:
        daily_repo = DailyRepositoryImpl()
        
        # 获取目标日期前20天的数据
        date_obj = datetime.strptime(target_date, '%Y-%m-%d')
        start_date = (date_obj - timedelta(days=20)).strftime('%Y-%m-%d')
        end_date = target_date
        
        klines = daily_repo.find_by_date_range(stock_code, start_date, end_date)
        
        if not klines:
            print(f"没有找到数据")
            return
        
        # 按日期降序排列（最新的在前）
        klines.sort(key=lambda x: x.date, reverse=True)
        
        print(f"找到 {len(klines)} 条数据")
        print(f"日期范围: {klines[-1].date} 至 {klines[0].date}\n")
            
        # 找到目标日期的索引（日期可能是字符串或datetime）
        target_idx = None
        for idx, k in enumerate(klines):
            k_date_str = k.date if isinstance(k.date, str) else k.date.strftime('%Y-%m-%d')
            if k_date_str == target_date or (hasattr(k.date, 'strftime') and k.date.strftime('%Y-%m-%d') == target_date):
                target_idx = idx
                break
        
        if target_idx is None:
            print(f"未找到目标日期 {target_date}")
            print(f"可用的日期列表（最近10天）:")
            for i, k in enumerate(klines[:10]):
                print(f"  {k.date}")
            return
        
        # 判断主板还是非主板
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        board_type = "主板" if is_main_board else "非主板"
        
        print(f"股票类型：{board_type}")
        print(f"\n目标日期：{target_date}")
        print(f"前5个交易日涨幅情况：\n")
        
        # 显示前5个交易日的数据
        print(f"{'日期':<15} {'开盘':<10} {'收盘':<10} {'涨跌幅':<12} {'是否阳线':<10}")
        print("-" * 80)
        
        change_pcts = []
        daily_list = []
        
        for i in range(target_idx + 1, min(target_idx + 6, len(klines))):
            k = klines[i]
            if k.pre_close and k.pre_close > 0:
                pct = (k.close - k.pre_close) / k.pre_close * 100
            else:
                pct = 0
            change_pcts.append(pct)
            daily_list.append(k)
            
            is_bullish = "是" if k.close >= k.open else "否"
            print(f"{k.date:<15} {k.open:<10.2f} {k.close:<10.2f} {pct:>10.2f}% {is_bullish:<10}")
        
        print(f"\n{'='*100}")
        print("不追涨插件检查（5种情况）：\n")
        
        # 情况1: 连续2个涨停
        limit_threshold = 10 if is_main_board else 20
        print(f"1. 连续2个涨停（阈值：{limit_threshold * 0.95:.1f}%）")
        if len(change_pcts) >= 2:
            if change_pcts[0] >= limit_threshold * 0.95 and change_pcts[1] >= limit_threshold * 0.95:
                print(f"   [触发] 前2日涨幅: {change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%")
            else:
                print(f"   [未触发] 前2日涨幅: {change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%")
        else:
            print(f"   [数据不足]")
        
        # 情况2: 前2日累计涨幅过大
        threshold_2days = 15 if is_main_board else 25
        print(f"\n2. 前2日累计涨幅过大（阈值：{threshold_2days}%）")
        if len(change_pcts) >= 2:
            cum_2days = sum(change_pcts[:2])
            if cum_2days > threshold_2days:
                print(f"   [触发] 累计涨幅: {cum_2days:.2f}% > {threshold_2days}%")
            else:
                print(f"   [未触发] 累计涨幅: {cum_2days:.2f}% <= {threshold_2days}%")
        else:
            print(f"   [数据不足]")
        
        # 情况3: 前3天累计涨幅过大
        threshold_3days = 20 if is_main_board else 30
        print(f"\n3. 前3日累计涨幅过大（阈值：{threshold_3days}%）")
        if len(change_pcts) >= 3:
            cum_3days = sum(change_pcts[:3])
            if cum_3days > threshold_3days:
                print(f"   [触发] 累计涨幅: {cum_3days:.2f}% > {threshold_3days}%")
            else:
                print(f"   [未触发] 累计涨幅: {cum_3days:.2f}% <= {threshold_3days}%")
        else:
            print(f"   [数据不足]")
        
        # 情况4: 连续5天涨幅过大
        threshold_5days = 30 if is_main_board else 40
        print(f"\n4. 前5日累计涨幅过大（阈值：{threshold_5days}%）")
        if len(change_pcts) >= 5:
            cum_5days = sum(change_pcts[:5])
            if cum_5days > threshold_5days:
                print(f"   [触发] 累计涨幅: {cum_5days:.2f}% > {threshold_5days}%")
            else:
                print(f"   [未触发] 累计涨幅: {cum_5days:.2f}% <= {threshold_5days}%")
        else:
            print(f"   [数据不足]")
        
        # 情况5: 前两日连阳，且每日涨幅均大于5%
        print(f"\n5. 前两日连阳且每日涨幅>5%")
        if len(change_pcts) >= 2 and len(daily_list) >= 2:
            is_d1_bullish = daily_list[0].close >= daily_list[0].open
            is_d2_bullish = daily_list[1].close >= daily_list[1].open
            if (change_pcts[0] > 5 and change_pcts[1] > 5 and is_d1_bullish and is_d2_bullish):
                print(f"   [触发] 前2日涨幅: {change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%, 均为阳线")
            else:
                print(f"   [未触发] 前2日涨幅: {change_pcts[0]:.2f}%, {change_pcts[1]:.2f}%")
                print(f"            阳线情况: 第1日={is_d1_bullish}, 第2日={is_d2_bullish}")
        else:
            print(f"   [数据不足]")
        
        print(f"\n{'='*100}")
            
    except Exception as e:
        print(f"\n检查失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='检查不追涨插件')
    parser.add_argument('stock', type=str, help='股票代码，如 SH600037')
    parser.add_argument('date', type=str, help='日期，格式：2025-06-10')
    
    args = parser.parse_args()
    
    check_no_chase_high(args.stock, args.date)
