"""检查K线序列和涨跌幅计算"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl


def check_kline_sequence(stock_code: str, end_date_str: str, days=25):
    """检查K线序列"""
    print("="*100)
    print(f"检查K线序列: {stock_code} 往前{days}天至{end_date_str}")
    print("="*100)
    
    daily_repo = DailyRepositoryImpl()
    
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    start_date = (end_date - timedelta(days=days+10)).strftime('%Y-%m-%d')
    end_date_str2 = end_date.strftime('%Y-%m-%d')
    
    # 查询数据
    all_data = daily_repo.find_by_date_range(stock_code, start_date, end_date_str2)
    
    # 只保留日线数据
    daily_data = [d for d in all_data if d.date.hour == 0 and d.date.minute == 0 and d.date.second == 0]
    daily_data.sort(key=lambda x: x.date)
    
    # 只显示最近days天
    if len(daily_data) > days:
        daily_data = daily_data[-days:]
    
    print(f"\n最近{len(daily_data)}个交易日的K线数据:\n")
    print(f"{'日期':<12} {'开盘':<8} {'收盘':<8} {'昨收':<8} {'涨跌幅%':<10}")
    print("-"*60)
    
    for i, d in enumerate(daily_data):
        change_pct = 0
        if d.pre_close and d.pre_close > 0:
            change_pct = (d.close - d.pre_close) / d.pre_close * 100
        
        date_str = d.date.strftime('%Y-%m-%d')
        print(f"{date_str:<12} {d.open:<8.2f} {d.close:<8.2f} {d.pre_close:<8.2f} {change_pct:<10.2f}")
    
    # 计算累计涨跌幅
    if len(daily_data) >= 3:
        cum_3 = sum((d.close - d.pre_close) / d.pre_close * 100 if d.pre_close > 0 else 0 for d in daily_data[-3:])
        print(f"\n前3日累计涨跌幅: {cum_3:.2f}%")
    
    if len(daily_data) >= 5:
        cum_5 = sum((d.close - d.pre_close) / d.pre_close * 100 if d.pre_close > 0 else 0 for d in daily_data[-5:])
        print(f"前5日累计涨跌幅: {cum_5:.2f}%")
    
    if len(daily_data) >= 15:
        cum_15 = sum((d.close - d.pre_close) / d.pre_close * 100 if d.pre_close > 0 else 0 for d in daily_data[-15:])
        print(f"前15日累计涨跌幅: {cum_15:.2f}%")
    
    if len(daily_data) >= 20:
        cum_20 = sum((d.close - d.pre_close) / d.pre_close * 100 if d.pre_close > 0 else 0 for d in daily_data[-20:])
        print(f"前20日累计涨跌幅: {cum_20:.2f}%")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python check_kline_sequence.py <股票代码> [日期]")
        print("示例: python check_kline_sequence.py SZ300564 2025-07-24")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    end_date = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime('%Y-%m-%d')
    check_kline_sequence(stock_code, end_date)

