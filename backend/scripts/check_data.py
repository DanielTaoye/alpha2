"""临时脚本：详细检查箱体回踩被跌破的所有条件"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.persistence.database import DatabaseConnection

stock_code = 'SZ300188'
check_date = '2025-09-02'

with DatabaseConnection.get_connection_context() as conn:
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    print(f'国投智能 {check_date} 箱体回踩被跌破 详细条件检查:')
    print('=' * 100)
    
    # 获取K线数据（从6月开始，用于计算前42日数据）
    sql_kline = """
        SELECT DATE(shi_jian) as date, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia
        FROM basic_data_sz300188
        WHERE DATE(shi_jian) BETWEEN '2025-06-01' AND '2025-09-03' AND peroid_type = '1day'
        ORDER BY shi_jian
    """
    cursor.execute(sql_kline)
    kline_list = list(cursor.fetchall())
    
    # 获取Daily Chance数据
    sql_chance = """
        SELECT DATE(date) as date, support_price
        FROM b_daily_chance
        WHERE stock_code = %s AND DATE(date) BETWEEN '2025-06-01' AND '2025-09-03'
        ORDER BY date
    """
    cursor.execute(sql_chance, (stock_code,))
    chances = {str(row['date']): row for row in cursor.fetchall()}
    
    # 找到检查日期的索引
    current_idx = None
    for i, k in enumerate(kline_list):
        if str(k['date']) == check_date:
            current_idx = i
            break
    
    if current_idx is None:
        print(f'未找到 {check_date} 的数据')
        exit()
    
    current_close = float(kline_list[current_idx]['shou_pan_jia'] or 0)
    print(f'\n当日收盘价: {current_close:.2f}')
    
    # === 步骤1: 找X日 ===
    print('\n' + '=' * 100)
    print('步骤1: 找X日（前20天最高价日）')
    print('-' * 100)
    
    x_day_high = 0
    x_day_idx = -1
    x_day_date = None
    
    print(f'搜索范围: 索引 {current_idx - 19} ~ {current_idx} (共20天)')
    for i in range(current_idx - 19, current_idx + 1):
        h = float(kline_list[i]['zui_gao_jia'] or 0)
        d = str(kline_list[i]['date'])
        if h > x_day_high:
            x_day_high = h
            x_day_idx = i
            x_day_date = d
    
    drop_ratio = (x_day_high - current_close) / x_day_high * 100
    print(f'X日: {x_day_date}, 最高价: {x_day_high:.2f}')
    print(f'回落幅度: ({x_day_high:.2f} - {current_close:.2f}) / {x_day_high:.2f} = {drop_ratio:.2f}%')
    print(f'条件1 (回落>20%): {"✅ 满足" if drop_ratio > 20 else "❌ 不满足"}')
    
    # === 步骤2: 找Y日和Z日 ===
    print('\n' + '=' * 100)
    print('步骤2: 从X日往前22天找Y日和Z日')
    print('-' * 100)
    
    box_start = x_day_idx - 22
    box_end = x_day_idx - 1
    print(f'搜索范围: 索引 {box_start} ~ {box_end} (X日往前22天，不含X日)')
    print(f'日期范围: {kline_list[box_start]["date"]} ~ {kline_list[box_end]["date"]}')
    
    # 找Y日
    y_day_high = None
    y_day_date = None
    for i in range(box_start, box_end + 1):
        h = float(kline_list[i]['zui_gao_jia'] or 0)
        if h > x_day_high:
            if y_day_high is None or h > y_day_high:
                y_day_high = h
                y_day_date = str(kline_list[i]['date'])
    
    # 找Z日
    z_day_low = None
    z_day_date = None
    for i in range(box_start, box_end + 1):
        l = float(kline_list[i]['zui_di_jia'] or 0)
        if z_day_low is None or l < z_day_low:
            z_day_low = l
            z_day_date = str(kline_list[i]['date'])
    
    if y_day_high:
        print(f'Y日: {y_day_date}, 最高价: {y_day_high:.2f} (比X日更高)')
    else:
        print(f'Y日: 无 (22天内没有比X日更高的)')
    print(f'Z日: {z_day_date}, 最低价: {z_day_low:.2f}')
    
    # === 步骤3: 箱体确认 ===
    print('\n' + '=' * 100)
    print('步骤3: 箱体确认')
    print('-' * 100)
    
    if y_day_high:
        box_gain = (y_day_high - z_day_low) / z_day_low * 100
        print(f'计算: (Y日{y_day_high:.2f} - Z日{z_day_low:.2f}) / Z日{z_day_low:.2f} = {box_gain:.2f}%')
    else:
        box_gain = (x_day_high - z_day_low) / z_day_low * 100
        print(f'计算: (X日{x_day_high:.2f} - Z日{z_day_low:.2f}) / Z日{z_day_low:.2f} = {box_gain:.2f}%')
    print(f'条件2 (箱体涨幅>20%): {"✅ 满足" if box_gain > 20 else "❌ 不满足"}')
    
    # === 步骤4: 跌破支撑位 ===
    print('\n' + '=' * 100)
    print('步骤4: 跌破前一日支撑位')
    print('-' * 100)
    
    prev_date = str(kline_list[current_idx - 1]['date'])
    prev_chance = chances.get(prev_date)
    support = float(prev_chance['support_price'] or 0) / 100 if prev_chance and prev_chance['support_price'] else 0
    
    print(f'前一交易日: {prev_date}')
    print(f'前一日支撑位: {support:.2f}')
    print(f'当日收盘价: {current_close:.2f}')
    is_break = current_close < support
    print(f'条件3 (跌破支撑): {"✅ 满足" if is_break else "❌ 不满足"} ({current_close:.2f} {"<" if is_break else ">"} {support:.2f})')
    
    # === 总结 ===
    print('\n' + '=' * 100)
    print('总结:')
    print('-' * 100)
    print(f'  条件1 回落>20%: {"✅" if drop_ratio > 20 else "❌"} ({drop_ratio:.2f}%)')
    print(f'  条件2 箱体>20%: {"✅" if box_gain > 20 else "❌"} ({box_gain:.2f}%)')
    print(f'  条件3 跌破支撑: {"✅" if is_break else "❌"} (收盘{current_close:.2f} vs 支撑{support:.2f})')
    print(f'  条件4 MACD死叉: 需要API数据')
    
    all_pass = drop_ratio > 20 and box_gain > 20 and is_break
    print(f'\n前3个条件是否全部满足: {"✅ 是" if all_pass else "❌ 否"}')
    
    # === 步骤5: MACD死叉检查 ===
    print('\n' + '=' * 100)
    print('步骤5: MACD死叉检查（前5个交易日内）')
    print('-' * 100)
    
    # 获取足够的数据来计算MACD
    sql_all = """
        SELECT DATE(shi_jian) as date, shou_pan_jia
        FROM basic_data_sz300188
        WHERE DATE(shi_jian) <= %s AND peroid_type = '1day'
        ORDER BY shi_jian
    """
    cursor.execute(sql_all, (check_date,))
    all_data = cursor.fetchall()
    closes = [float(r['shou_pan_jia'] or 0) for r in all_data]
    dates_list = [str(r['date']) for r in all_data]
    
    # 计算EMA
    def calc_ema(prices, period):
        ema = [None] * len(prices)
        if len(prices) < period:
            return ema
        multiplier = 2.0 / (period + 1)
        sma = sum(prices[:period]) / period
        ema[period - 1] = sma
        for i in range(period, len(prices)):
            ema[i] = ema[i-1] * (1 - multiplier) + prices[i] * multiplier
        return ema
    
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    
    # 计算DIF
    dif = [None] * len(closes)
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            dif[i] = ema12[i] - ema26[i]
    
    # 计算DEA
    dea = [None] * len(closes)
    first_dif_idx = next((i for i, v in enumerate(dif) if v is not None), None)
    if first_dif_idx is not None:
        dif_values = [v for v in dif[first_dif_idx:first_dif_idx+9] if v is not None]
        if len(dif_values) == 9:
            dea[first_dif_idx + 8] = sum(dif_values) / 9
            for i in range(first_dif_idx + 9, len(closes)):
                if dif[i] is not None and dea[i-1] is not None:
                    dea[i] = dea[i-1] * 0.8 + dif[i] * 0.2
    
    # 找到检查日期的索引
    check_idx = dates_list.index(check_date) if check_date in dates_list else -1
    
    print(f'检查范围: 前20个交易日（找死叉转换点）')
    print(f'{"日期":<12} {"DIF":<10} {"DEA":<10} {"状态":<15}')
    print('-' * 50)
    
    death_cross_found = False
    death_cross_date = None
    for i in range(max(1, check_idx - 20), check_idx + 1):
        d = dates_list[i]
        curr_dif = dif[i]
        curr_dea = dea[i]
        prev_dif = dif[i-1] if i > 0 else None
        prev_dea = dea[i-1] if i > 0 else None
        
        status = ''
        if all(v is not None for v in [curr_dif, curr_dea, prev_dif, prev_dea]):
            if prev_dif > prev_dea and curr_dif < curr_dea:
                status = '🔴 死叉转换点!'
                # 记录最近的死叉转换点
                death_cross_found = True
                death_cross_date = d
            elif curr_dif > curr_dea:
                status = '金叉状态'
            else:
                status = '死叉状态'
        
        dif_str = f'{curr_dif:.4f}' if curr_dif else '-'
        dea_str = f'{curr_dea:.4f}' if curr_dea else '-'
        print(f'{d:<12} {dif_str:<10} {dea_str:<10} {status:<15}')
    
    # 检查死叉是否在前5天内
    if death_cross_found and death_cross_date:
        death_idx = dates_list.index(death_cross_date)
        days_ago = check_idx - death_idx
        in_5_days = days_ago <= 5
        print(f'\n死叉转换点: {death_cross_date} (距今{days_ago}个交易日)')
        print(f'条件4 (MACD死叉在前5天内): {"✅ 满足" if in_5_days else "❌ 不满足 (超过5天)"}')
        death_cross_found = in_5_days
    else:
        print(f'\n条件4 (MACD死叉): ❌ 不满足 (未找到死叉转换点)')
    
    # 最终结论
    print('\n' + '=' * 100)
    print('最终结论:')
    print('-' * 100)
    final_pass = all_pass and death_cross_found
    print(f'  全部4个条件是否满足: {"✅ 是 → 应该触发箱体回踩R点!" if final_pass else "❌ 否"}')

