"""分析股票涨幅统计"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl


def analyze_stock_gains(stock_code: str, start_date_str: str, end_date_str: str):
    """分析股票涨幅统计"""
    print("="*100)
    print(f"股票涨幅分析: {stock_code} 从 {start_date_str} 到 {end_date_str}")
    print("="*100)
    
    daily_repo = DailyRepositoryImpl()
    daily_chance_repo = DailyChanceRepositoryImpl()
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    
    query_start = (start_date - timedelta(days=30)).strftime('%Y-%m-%d')
    query_end = end_date.strftime('%Y-%m-%d')
    
    # 只查询日线数据
    daily_data_list = []
    all_data = daily_repo.find_by_date_range(stock_code, query_start, query_end)
    for d in all_data:
        if d.date.hour == 0 and d.date.minute == 0:
            daily_data_list.append(d)
    
    daily_data_list.sort(key=lambda x: x.date)
    
    print(f"查询到 {len(daily_data_list)} 条日线数据\n")
    
    # 主板还是非主板
    is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
    board_type = "主板" if is_main_board else "创业板/科创板"
    print(f"股票类型: {board_type}\n")
    
    # 统计涨幅
    max_3day_gain = 0
    max_5day_gain = 0
    max_15day_gain = 0
    max_20day_gain = 0
    max_3day_date = None
    max_5day_date = None
    max_15day_date = None
    max_20day_date = None
    
    for i in range(len(daily_data_list)):
        # 计算往前N日的涨幅
        if i >= 3:
            gains = []
            for j in range(1, 4):  # 前3日
                if daily_data_list[i-j].pre_close and daily_data_list[i-j].pre_close > 0:
                    gain = (daily_data_list[i-j].close - daily_data_list[i-j].pre_close) / daily_data_list[i-j].pre_close * 100
                    gains.append(gain)
            if gains:
                gain_3day = sum(gains)
                if gain_3day > max_3day_gain:
                    max_3day_gain = gain_3day
                    max_3day_date = daily_data_list[i].date.strftime('%Y-%m-%d')
        
        if i >= 5:
            gains = []
            for j in range(1, 6):  # 前5日
                if daily_data_list[i-j].pre_close and daily_data_list[i-j].pre_close > 0:
                    gain = (daily_data_list[i-j].close - daily_data_list[i-j].pre_close) / daily_data_list[i-j].pre_close * 100
                    gains.append(gain)
            if gains:
                gain_5day = sum(gains)
                if gain_5day > max_5day_gain:
                    max_5day_gain = gain_5day
                    max_5day_date = daily_data_list[i].date.strftime('%Y-%m-%d')
        
        if i >= 15:
            gains = []
            for j in range(1, 16):  # 前15日
                if daily_data_list[i-j].pre_close and daily_data_list[i-j].pre_close > 0:
                    gain = (daily_data_list[i-j].close - daily_data_list[i-j].pre_close) / daily_data_list[i-j].pre_close * 100
                    gains.append(gain)
            if gains:
                gain_15day = sum(gains)
                if gain_15day > max_15day_gain:
                    max_15day_gain = gain_15day
                    max_15day_date = daily_data_list[i].date.strftime('%Y-%m-%d')
        
        if i >= 20:
            gains = []
            for j in range(1, 21):  # 前20日
                if daily_data_list[i-j].pre_close and daily_data_list[i-j].pre_close > 0:
                    gain = (daily_data_list[i-j].close - daily_data_list[i-j].pre_close) / daily_data_list[i-j].pre_close * 100
                    gains.append(gain)
            if gains:
                gain_20day = sum(gains)
                if gain_20day > max_20day_gain:
                    max_20day_gain = gain_20day
                    max_20day_date = daily_data_list[i].date.strftime('%Y-%m-%d')
    
    # 输出统计结果
    print("="*100)
    print("涨幅统计结果:")
    print("="*100)
    threshold_3days = 15 if is_main_board else 20
    threshold_5days = 20 if is_main_board else 25
    
    print(f"\n前3日最大涨幅: {max_3day_gain:.2f}% (阈值:{threshold_3days}%) 日期:{max_3day_date}")
    if max_3day_gain > threshold_3days:
        print(f"  [OK] 满足条件2触发阈值")
    else:
        print(f"  [NO] 未满足条件2触发阈值 (差距:{threshold_3days-max_3day_gain:.2f}%)")
    
    print(f"\n前5日最大涨幅: {max_5day_gain:.2f}% (阈值:{threshold_5days}%) 日期:{max_5day_date}")
    if max_5day_gain > threshold_5days:
        print(f"  [OK] 满足条件3触发阈值")
    else:
        print(f"  [NO] 未满足条件3触发阈值 (差距:{threshold_5days-max_5day_gain:.2f}%)")
    
    print(f"\n前15日最大涨幅: {max_15day_gain:.2f}% (阈值:50%) 日期:{max_15day_date}")
    if max_15day_gain > 50:
        print(f"  [OK] 满足条件5触发阈值")
    else:
        print(f"  [NO] 未满足条件5触发阈值 (差距:{50-max_15day_gain:.2f}%)")
    
    print(f"\n前20日最大涨幅: {max_20day_gain:.2f}% (阈值:50%) 日期:{max_20day_date}")
    if max_20day_gain > 50:
        print(f"  [OK] 满足条件6触发阈值")
    else:
        print(f"  [NO] 未满足条件6触发阈值 (差距:{50-max_20day_gain:.2f}%)")
    
    print("\n" + "="*100)
    print("结论: 如果所有条件都未满足，说明该股票在此期间没有出现符合乖离率偏离的大幅上涨。")
    print("建议: 选择一个有明显上涨趋势的股票/时间段进行测试。")
    print("="*100)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python analyze_stock_gains.py <股票代码> <开始日期> <结束日期>")
        print("示例: python analyze_stock_gains.py SZ300564 2025-01-01 2025-11-30")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    start_date = sys.argv[2]
    end_date = sys.argv[3]
    
    analyze_stock_gains(stock_code, start_date, end_date)

