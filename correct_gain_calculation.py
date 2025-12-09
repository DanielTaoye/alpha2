#!/usr/bin/env python3
"""
正确计算中集车辆前N日涨跌幅
方法：(当天收盘价 - N天前收盘价) / N天前收盘价
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
            SELECT shi_jian, shou_pan_jia
            FROM `{table_name}`
            WHERE DATE(shi_jian) BETWEEN %s AND %s
              AND peroid_type = '1day'
            ORDER BY shi_jian ASC
        """

        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall()

        # 收集数据
        data_list = []
        for row in rows:
            shi_jian, shou_pan = row
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

        current_close = data_list[target_idx]['close']
        print("=" * 80)
        print(f"中集车辆(SZ301039) 2024-10-08收盘价: {current_close:.2f}元")
        print("=" * 80)

        # 计算前N日涨幅：(当天收盘价 - N天前收盘价) / N天前收盘价
        print("\n正确的涨跌幅计算方法：")
        print("(当天收盘价 - N天前收盘价) / N天前收盘价")
        print("-" * 80)

        # 前1日涨幅
        if target_idx > 0:
            prev_1_day = data_list[target_idx - 1]
            gain_1 = (current_close - prev_1_day['close']) / prev_1_day['close'] * 100
            print(".2f")

        # 前3日涨幅
        if target_idx >= 3:
            prev_3_day = data_list[target_idx - 3]
            gain_3 = (current_close - prev_3_day['close']) / prev_3_day['close'] * 100
            print(".2f")

        # 前5日涨幅
        if target_idx >= 5:
            prev_5_day = data_list[target_idx - 5]
            gain_5 = (current_close - prev_5_day['close']) / prev_5_day['close'] * 100
            print(".2f")

        # 前15日涨幅
        if target_idx >= 15:
            prev_15_day = data_list[target_idx - 15]
            gain_15 = (current_close - prev_15_day['close']) / prev_15_day['close'] * 100
            print(".2f")

        # 前20日涨幅
        if target_idx >= 20:
            prev_20_day = data_list[target_idx - 20]
            gain_20 = (current_close - prev_20_day['close']) / prev_20_day['close'] * 100
            print(".2f")

        print("\n" + "=" * 80)
        print("详细的日期和价格对照")
        print("=" * 80)

        # 显示相关的日期和价格
        print("\n当天 (2024-10-08):")
        print(".2f")

        if target_idx > 0:
            prev_1 = data_list[target_idx - 1]
            print("\n前1日 (2024-09-30):")
            print(".2f")

        if target_idx >= 3:
            prev_3 = data_list[target_idx - 3]
            print("\n前3日 (2024-09-26):")
            print(".2f")

        if target_idx >= 5:
            prev_5 = data_list[target_idx - 5]
            print("\n前5日 (2024-09-23):")
            print(".2f")

        if target_idx >= 15:
            prev_15 = data_list[target_idx - 15]
            print("\n前15日:")
            print(f"日期: {prev_15['date']}, 收盘价: {prev_15['close']:.2f}")

        if target_idx >= 20:
            prev_20 = data_list[target_idx - 20]
            print("\n前20日:")
            print(f"日期: {prev_20['date']}, 收盘价: {prev_20['close']:.2f}")

        print("\n" + "=" * 80)
        print("乖离率偏离插件触发条件检查")
        print("=" * 80)

        # 检查是否会触发乖离率偏离
        triggered_conditions = []

        # 条件1: 连续2个以上涨停（需要检查涨幅是否>=19.8%）
        # 这里暂时跳过，因为需要检查连续涨停

        # 条件2: 前3日涨幅过大
        if target_idx >= 3:
            prev_3 = data_list[target_idx - 3]
            gain_3 = (current_close - prev_3['close']) / prev_3['close'] * 100
            threshold_3 = 20  # 非主板阈值
            if gain_3 > threshold_3:
                triggered_conditions.append(f"条件2: 前3日涨幅{gain_3:.2f}% > {threshold_3}%")

        # 条件3: 前5日涨幅过大
        if target_idx >= 5:
            prev_5 = data_list[target_idx - 5]
            gain_5 = (current_close - prev_5['close']) / prev_5['close'] * 100
            threshold_5 = 25  # 非主板阈值
            if gain_5 > threshold_5:
                triggered_conditions.append(f"条件3: 前5日涨幅{gain_5:.2f}% > {threshold_5}%")

        # 条件5: 前15日涨幅>50%
        if target_idx >= 15:
            prev_15 = data_list[target_idx - 15]
            gain_15 = (current_close - prev_15['close']) / prev_15['close'] * 100
            if gain_15 > 50:
                triggered_conditions.append(f"条件5: 前15日涨幅{gain_15:.2f}% > 50%")

        # 条件6: 前20日涨幅>50%
        if target_idx >= 20:
            prev_20 = data_list[target_idx - 20]
            gain_20 = (current_close - prev_20['close']) / prev_20['close'] * 100
            if gain_20 > 50:
                triggered_conditions.append(f"条件6: 前20日涨幅{gain_20:.2f}% > 50%")

        if triggered_conditions:
            print("❌ 会触发乖离率偏离插件:")
            for condition in triggered_conditions:
                print(f"   {condition}")
        else:
            print("✅ 不会触发乖离率偏离插件（涨幅均未达到阈值）")

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
