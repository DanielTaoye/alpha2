#!/usr/bin/env python3
"""
正确计算中集车辆(SZ301039) 2024年10月8号前几天的涨跌幅
"""

import pymysql

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}


def main():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 查询2024年9-10月的日线数据
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

        print("=" * 80)
        print("中集车辆(SZ301039) 2024年10月8号前后的交易日数据")
        print("=" * 80)

        # 收集数据
        data_list = []
        for row in rows:
            shi_jian, kai_pan, gao, di, shou_pan, liang, shang_yu = row
            date_str = shi_jian.strftime('%Y-%m-%d') if shi_jian else ''
            close_price = float(shou_pan) if shou_pan else 0

            data_list.append({
                'date': date_str,
                'close': close_price
            })

        # 找到2024-10-08的位置
        target_idx = None
        for i, data in enumerate(data_list):
            if data['date'] == '2024-10-08':
                target_idx = i
                break

        if target_idx is None:
            print("❌ 未找到2024-10-08的数据")
            return

        print(f"目标日期 2024-10-08 是第 {target_idx + 1} 个交易日")
        print(f"数据库中共有 {len(data_list)} 个交易日数据")

        # 显示2024-10-08前后的交易日
        print("\n2024-10-08 前后的交易日:")
        start_idx = max(0, target_idx - 7)
        end_idx = min(len(data_list), target_idx + 3)

        for i in range(start_idx, end_idx):
            data = data_list[i]
            marker = ""
            if data['date'] == '2024-10-08':
                marker = " <-- 目标日期"
            elif i < target_idx:
                days_before = target_idx - i
                marker = f" <-- 前{days_before}日"

            print("<12")

        # 计算前几日的涨幅
        print("\n" + "=" * 80)
        print("涨幅计算结果")
        print("=" * 80)

        # 前1日涨幅
        if target_idx > 0:
            prev_day = data_list[target_idx - 1]
            current_day = data_list[target_idx]
            change_pct = (current_day['close'] - prev_day['close']) / prev_day['close'] * 100
            print(".2f")

        # 前3日涨幅
        if target_idx >= 3:
            print("\n前3日涨幅计算:")
            total_change = 0
            for i in range(target_idx - 3, target_idx):
                prev_close = data_list[i-1]['close'] if i > 0 else data_list[i]['close']
                current_close = data_list[i]['close']
                day_change = (current_close - prev_close) / prev_close * 100
                print(".2f")
                total_change += day_change
            print(".2f")

        # 前5日涨幅
        if target_idx >= 5:
            print("\n前5日涨幅计算:")
            total_change = 0
            for i in range(target_idx - 5, target_idx):
                prev_close = data_list[i-1]['close'] if i > 0 else data_list[i]['close']
                current_close = data_list[i]['close']
                day_change = (current_close - prev_close) / prev_close * 100
                print(".2f")
                total_change += day_change
            print(".2f")

        # 解释国庆假期
        print("\n" + "=" * 80)
        print("国庆假期说明")
        print("=" * 80)
        print("2024年国庆假期: 2024-09-28 至 2024-10-07")
        print("所以2024-10-08的前一个交易日是2024-09-30")
        print("前3个交易日是: 2024-09-26, 2024-09-27, 2024-09-30")

        print("\n✅ 数据来源于数据库的真实日线数据")
        print("✅ 计算方法：当前收盘价相对前一日收盘价的涨跌幅")
        print("✅ 非交易日（周末、国庆假期）无数据，故跳过")

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
    main()
