#!/usr/bin/env python3
"""
查询中集车辆(SZ301039) 2024年10月8号前几天的涨跌幅
"""

import sys
import os
import pymysql
from datetime import datetime, timedelta

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}


def query_sz301039_data():
    """查询中集车辆数据"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 查询2024年10月8号前后几天的日线数据
        table_name = 'basic_data_sz301039'
        start_date = '2024-09-25'  # 往前多查几天
        end_date = '2024-10-15'    # 往后多查几天

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
        print("中集车辆(SZ301039) 2024年10月8号前后日线数据")
        print("=" * 80)
        print("<10")

        # 用于计算真实涨幅
        prev_close = None
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
            change_pct_db = float(shang_yu) if shang_yu else 0  # 数据库中的涨跌幅

            # 计算真实涨幅（使用前一日收盘价）
            real_change_pct = 0
            if prev_close and prev_close > 0:
                real_change_pct = (close_price - prev_close) / prev_close * 100

            # 标记2024-10-08这一天
            marker = " <-- 目标日期" if date_str == '2024-10-08' else ""

            print("<10")

            # 保存数据用于后续分析
            data_list.append({
                'date': date_str,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
                'db_change_pct': change_pct_db,
                'real_change_pct': real_change_pct
            })

            prev_close = close_price

        # 分析2024-10-08前几天的涨幅
        print("\n" + "=" * 80)
        print("2024年10月8号前几天的涨幅分析")
        print("=" * 80)

        # 找到目标日期的索引
        target_idx = None
        for i, data in enumerate(data_list):
            if data['date'] == '2024-10-08':
                target_idx = i
                break

        if target_idx is not None:
            print("\n前1日涨幅:")
            if target_idx > 0:
                prev1 = data_list[target_idx - 1]
                print(".2f")

            print("\n前3日涨幅:")
            if target_idx >= 3:
                cum_3days = sum(data_list[i]['real_change_pct'] for i in range(target_idx-3, target_idx))
                print(".2f")
                # 详细列出
                for i in range(target_idx-3, target_idx):
                    data = data_list[i]
                    print(".2f")

            print("\n前5日涨幅:")
            if target_idx >= 5:
                cum_5days = sum(data_list[i]['real_change_pct'] for i in range(target_idx-5, target_idx))
                print(".2f")
                # 详细列出
                for i in range(target_idx-5, target_idx):
                    data = data_list[i]
                    print(".2f")

            print("\n前15日涨幅:")
            if target_idx >= 15:
                cum_15days = sum(data_list[i]['real_change_pct'] for i in range(target_idx-15, target_idx))
                print(".2f")

            print("\n前20日涨幅:")
            if target_idx >= 20:
                cum_20days = sum(data_list[i]['real_change_pct'] for i in range(target_idx-20, target_idx))
                print(".2f")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    query_sz301039_data()
