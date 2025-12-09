#!/usr/bin/env python3
"""
检查中集车辆(SZ301039) 2024年10月的交易日数据
验证涨幅计算的准确性
"""

import pymysql
from datetime import datetime, timedelta

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}


def check_trading_days():
    """检查交易日数据"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 查询2024年9-10月的日线数据，确保有足够的历史数据
        table_name = 'basic_data_sz301039'
        start_date = '2024-09-01'
        end_date = '2024-10-31'

        sql = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
                   cheng_jiao_liang, shang_yu_bi
            FROM `{table_name}`
            WHERE DATE(shi_jian) BETWEEN %s AND %s
              AND peroid_type = '1day'
            ORDER BY shi_jian ASC
        """

        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall()

        print("=" * 120)
        print("中集车辆(SZ301039) 2024年10月交易日数据")
        print("=" * 120)
        print("<12")

        # 存储数据用于分析
        data_list = []

        for row in rows:
            shi_jian, kai_pan, gao, di, shou_pan, liang, shang_yu = row

            # 转换数据类型
            date_str = shi_jian.strftime('%Y-%m-%d') if shi_jian else ''
            open_price = float(kai_pan) if kai_pan else 0
            high_price = float(gao) if gao else 0
            low_price = float(di) if di else 0
            close_price = float(shou_pan) if shou_pan else 0
            volume = int(liang) if liang else 0
            change_pct_db = float(shang_yu) if shang_yu else 0

            print("<12")

            data_list.append({
                'date': date_str,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
                'db_change_pct': change_pct_db
            })

        print("\n" + "=" * 120)
        print("详细涨幅计算过程")
        print("=" * 120)

        # 按日期顺序计算涨幅
        prev_close = None
        for i, data in enumerate(data_list):
            if prev_close is not None and prev_close > 0:
                real_change_pct = (data['close'] - prev_close) / prev_close * 100
                print("<12")
            else:
                print("<12")
            prev_close = data['close']

        print("\n" + "=" * 120)
        print("手动验证2024-10-08的前几日涨幅计算")
        print("=" * 120)

        # 找到2024-10-08的位置
        target_idx = None
        for i, data in enumerate(data_list):
            if data['date'] == '2024-10-08':
                target_idx = i
                break

        if target_idx is not None:
            print(f"目标日期 2024-10-08 的位置: 第{target_idx + 1}条记录")
            print(f"数据库中实际存在的日期数量: {len(data_list)}")

            # 显示前几天的日期
            print("\n前几天的实际日期:")
            for i in range(max(0, target_idx-5), target_idx):
                if i >= 0:
                    data = data_list[i]
                    days_ago = target_idx - i
                    print(f"  前{days_ago}日: {data['date']}")

            # 计算前3日的涨幅
            if target_idx >= 3:
                print("\n前3日涨幅计算:")
                total_change = 0
                for i in range(target_idx-3, target_idx):
                    prev_close = data_list[i-1]['close'] if i > 0 else data_list[i]['close']
                    current_close = data_list[i]['close']
                    if prev_close > 0:
                        day_change = (current_close - prev_close) / prev_close * 100
                        print(".2f")
                        total_change += day_change
                print(".2f")

        # 检查是否是周末或节假日
        print("\n" + "=" * 120)
        print("日期类型分析")
        print("=" * 120)

        from datetime import datetime
        for data in data_list:
            date_obj = datetime.strptime(data['date'], '%Y-%m-%d')
            weekday = date_obj.strftime('%A')  # 英文星期名
            weekday_cn = {
                'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
                'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
            }.get(weekday, weekday)

            marker = ""
            if data['date'] == '2024-10-08':
                marker = " <-- 目标日期"
            elif data['date'] in ['2024-10-05', '2024-10-06', '2024-10-07']:
                marker = " <-- 前3日"

            print("<12")

    except Exception as e:
        print(f"查询失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    check_trading_days()
