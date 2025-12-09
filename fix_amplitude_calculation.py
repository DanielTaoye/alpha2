#!/usr/bin/env python3
"""
修复振幅计算问题 - 当pre_close为0时使用开盘价作为基准
"""

import sys
import os
import pymysql

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)


def fix_amplitude_calculation():
    """修复振幅计算问题"""
    try:
        # 查询中集车辆2024-10-08的数据
        table_name = 'basic_data_sz301039'
        test_date = '2024-10-08'

        # 数据库配置
        DB_CONFIG = {
            'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
            'port': 21648,
            'user': 'root',
            'password': 'MrEPYZus7myr',
            'database': 'stock',
            'charset': 'utf8mb4'
        }

        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        sql = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia
            FROM `{table_name}`
            WHERE DATE(shi_jian) = %s
        """

        cursor.execute(sql, (test_date,))
        row = cursor.fetchone()

        if not row:
            print("❌ 未找到数据")
            return

        shi_jian, kai_pan, gao, di, shou_pan = row

        open_price = float(kai_pan) if kai_pan else 0
        high_price = float(gao) if gao else 0
        low_price = float(di) if di else 0
        close_price = float(shou_pan) if shou_pan else 0

        print("=" * 80)
        print("中集车辆(SZ301039) 2024-10-08 振幅计算分析")
        print("=" * 80)
        print(f"开盘价: {open_price:.2f}")
        print(f"最高价: {high_price:.2f}")
        print(f"最低价: {low_price:.2f}")
        print(f"收盘价: {close_price:.2f}")

        # 当前振幅计算（使用前收价）
        pre_close = 0  # 数据库中是0
        current_amplitude = ((high_price - low_price) / pre_close * 100) if pre_close > 0 else 0
        print(f"\n当前振幅计算（使用前收价{pre_close}）: {current_amplitude:.2f}%")

        # 修复方案1：使用开盘价作为基准
        amplitude_with_open = ((high_price - low_price) / open_price * 100) if open_price > 0 else 0
        print(f"修复方案1（使用开盘价{open_price:.2f}）: {amplitude_with_open:.2f}%")

        # 修复方案2：使用收盘价作为基准
        amplitude_with_close = ((high_price - low_price) / close_price * 100) if close_price > 0 else 0
        print(f"修复方案2（使用收盘价{close_price:.2f}）: {amplitude_with_close:.2f}%")

        # 判断主板/非主板阈值
        stock_code = "SZ301039"
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        threshold = 6.0 if is_main_board else 8.0

        print(f"\n股票类型: {'主板' if is_main_board else '非主板'}")
        print(f"振幅阈值: {threshold}%")

        print("\n方案对比:")
        print(f"当前方案: {current_amplitude:.2f}% {'✅' if current_amplitude > threshold else '❌'}")
        print(f"开盘价基准: {amplitude_with_open:.2f}% {'✅' if amplitude_with_open > threshold else '❌'}")
        print(f"收盘价基准: {amplitude_with_close:.2f}% {'✅' if amplitude_with_close > threshold else '❌'}")

        # 计算实际合理的振幅（使用开盘价）
        if amplitude_with_open > threshold:
            print("\n🎯 结论: 使用开盘价作为基准，中集车辆2024-10-08的振幅足够，会触发R点信号！")
        else:
            print("\n🎯 结论: 即使修复振幅计算，中集车辆2024-10-08的振幅仍不够，不会触发R点信号。")
        # 检查前一日数据作为参考
        prev_date = '2024-10-07'
        cursor.execute(sql, (prev_date,))
        prev_row = cursor.fetchone()

        if prev_row:
            _, prev_kai_pan, _, _, prev_shou_pan = prev_row
            prev_close_price = float(prev_shou_pan) if prev_shou_pan else 0
            print(f"\n前一日收盘价: {prev_close_price:.2f}")
            amplitude_with_prev_close = ((high_price - low_price) / prev_close_price * 100) if prev_close_price > 0 else 0
            print(f"使用前一日收盘价计算振幅: {amplitude_with_prev_close:.2f}% {'✅' if amplitude_with_prev_close > threshold else '❌'}")

    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    fix_amplitude_calculation()
