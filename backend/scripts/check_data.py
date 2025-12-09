"""临时脚本：批量检查国投智能的R点条件"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.persistence.database import DatabaseConnection

stock_code = 'SZ300188'

with DatabaseConnection.get_connection_context() as conn:
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    # 查询2025-08-15到2025-09-03的K线数据（多取几天用于计算前20日最高价）
    print('国投智能 2025-08-20 ~ 2025-09-03 箱体回踩被跌破R点条件检查:')
    print('=' * 120)
    
    # 获取K线数据（从7月开始，用于计算前20日最高价）
    sql_kline = """
        SELECT DATE(shi_jian) as date, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia
        FROM basic_data_sz300188
        WHERE DATE(shi_jian) BETWEEN '2025-07-01' AND '2025-09-03' AND peroid_type = '1day'
        ORDER BY shi_jian
    """
    cursor.execute(sql_kline)
    all_klines = cursor.fetchall()
    kline_list = list(all_klines)
    klines = {str(row['date']): row for row in all_klines}
    
    # 获取Daily Chance数据
    sql_chance = """
        SELECT DATE(date) as date, support_price, pressure_price, volume_type, bearish_pattern
        FROM b_daily_chance
        WHERE stock_code = %s AND DATE(date) BETWEEN '2025-07-01' AND '2025-09-03'
        ORDER BY date
    """
    cursor.execute(sql_chance, (stock_code,))
    chances = {str(row['date']): row for row in cursor.fetchall()}
    
    # 逐日分析
    dates = ['2025-08-20', '2025-08-21', '2025-08-22', '2025-08-25', '2025-08-26', 
             '2025-08-27', '2025-08-28', '2025-08-29', '2025-09-01', '2025-09-02', '2025-09-03']
    
    print(f'{"日期":<12} {"收盘":<8} {"前20日高":<10} {"回落%":<8} {"支撑位":<8} {"跌破?":<6} {"量型":<12}')
    print('-' * 120)
    
    for date in dates:
        kline = klines.get(date)
        if not kline:
            print(f'{date:<12} 无K线数据')
            continue
        
        # 找到当前日期在kline_list中的索引
        current_idx = None
        for i, k in enumerate(kline_list):
            if str(k['date']) == date:
                current_idx = i
                break
        
        if current_idx is None or current_idx < 20:
            print(f'{date:<12} 数据不足20天')
            continue
        
        close = float(kline['shou_pan_jia'] or 0)
        
        # 计算前20日最高价
        high_20 = 0
        for i in range(current_idx - 19, current_idx + 1):
            h = float(kline_list[i]['zui_gao_jia'] or 0)
            if h > high_20:
                high_20 = h
        
        # 计算回落幅度
        drop_pct = (high_20 - close) / high_20 * 100 if high_20 > 0 else 0
        drop_ok = '✅' if drop_pct > 18 else '❌'
        
        # 找前一交易日
        prev_date = str(kline_list[current_idx - 1]['date']) if current_idx > 0 else None
        prev_chance = chances.get(prev_date) if prev_date else None
        
        # 前一日支撑位
        support = float(prev_chance['support_price'] or 0) / 100 if prev_chance and prev_chance['support_price'] else 0
        is_break = '✅' if close < support and support > 0 else '❌'
        
        # 当日量型
        chance = chances.get(date)
        vol_type = chance['volume_type'] if chance else '-'
        
        print(f'{date:<12} {close:<8.2f} {high_20:<10.2f} {drop_pct:<6.1f}%{drop_ok} {support:<8.2f} {is_break:<6} {vol_type:<12}')
    
    print('\n' + '=' * 120)
    print('箱体回踩被跌破条件:')
    print('  1. 前20日最高价距当前价格 > 18% ✅')
    print('  2. 箱体确认（涨幅>20%）')
    print('  3. 跌破前一日支撑位 ✅')
    print('  4. MACD死叉（前5日内）')

