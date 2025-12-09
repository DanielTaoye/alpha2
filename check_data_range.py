#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from config_production_master import DATABASE_CONFIG as MASTER_DB_CONFIG
import pymysql

def connect_database():
    """连接数据库"""
    return pymysql.connect(
        host=MASTER_DB_CONFIG['host'],
        port=MASTER_DB_CONFIG['port'],
        user=MASTER_DB_CONFIG['user'],
        password=MASTER_DB_CONFIG['password'],
        database=MASTER_DB_CONFIG['database'],
        charset='utf8mb4'
    )

def check_data_range():
    """检查数据时间范围"""
    stock_code = "SZ301039"
    table_name = f"basic_data_{stock_code.lower()}"
    
    conn = connect_database()
    cursor = conn.cursor()
    
    print(f"=== 检查 {stock_code} 数据时间范围 ===")
    
    try:
        # 1. 检查数据时间范围
        range_sql = f"""
        SELECT 
            MIN(DATE(shi_jian)) as earliest_date,
            MAX(DATE(shi_jian)) as latest_date,
            COUNT(*) as total_records,
            COUNT(DISTINCT DATE(shi_jian)) as trading_days
        FROM {table_name}
        WHERE peroid_type = '1day'
        """
        cursor.execute(range_sql)
        result = cursor.fetchone()
        earliest, latest, total, trading_days = result
        
        print(f"数据时间范围: {earliest} 至 {latest}")
        print(f"总记录数: {total}")
        print(f"交易日数: {trading_days}")
        
        # 2. 检查2024年数据
        print(f"\n2024年数据检查:")
        recent_2024_sql = f"""
        SELECT DATE(shi_jian) as date, shou_pan_jia, shang_yu_bi
        FROM {table_name}
        WHERE peroid_type = '1day'
          AND DATE(shi_jian) >= '2024-01-01'
          AND DATE(shi_jian) <= '2024-12-31'
        ORDER BY DATE(shi_jian) ASC
        LIMIT 20
        """
        cursor.execute(recent_2024_sql)
        recent_2024 = cursor.fetchall()
        
        if recent_2024:
            print("2024年最近数据:")
            for row in recent_2024[-10:]:  # 显示最后10条
                date_str, close_p, change_pct = row
                print(f"{date_str}: 收盘{close_p}, 涨跌幅{change_pct}")
        else:
            print("❌ 没有2024年数据！")
        
        # 3. 检查2023年数据
        print(f"\n2023年数据检查:")
        recent_2023_sql = f"""
        SELECT DATE(shi_jian) as date, shou_pan_jia
        FROM {table_name}
        WHERE peroid_type = '1day'
          AND DATE(shi_jian) >= '2023-01-01'
          AND DATE(shi_jian) <= '2023-12-31'
        ORDER BY DATE(shi_jian) DESC
        LIMIT 10
        """
        cursor.execute(recent_2023_sql)
        recent_2023 = cursor.fetchall()
        
        if recent_2023:
            print("2023年最后几条数据:")
            for row in recent_2023:
                date_str, close_p = row
                print(f"{date_str}: 收盘{close_p}")
        else:
            print("❌ 没有2023年数据！")
        
        # 4. 检查最近的交易日数据
        print(f"\n最近30个交易日数据:")
        latest_sql = f"""
        SELECT DATE(shi_jian) as date, shou_pan_jia, shang_yu_bi
        FROM {table_name}
        WHERE peroid_type = '1day'
        ORDER BY DATE(shi_jian) DESC
        LIMIT 30
        """
        cursor.execute(latest_sql)
        latest_data = cursor.fetchall()
        
        print("最近30个交易日:")
        for i, (date_str, close_p, change_pct) in enumerate(latest_data):
            print(f"{i+1:2d}. {date_str}: 收盘{close_p}, 涨跌幅{change_pct}")
            
        # 5. 检查是否有跳跃的数据（不是连续交易日）
        print(f"\n数据连续性检查:")
        prev_date = None
        gaps = []
        for i, (date_str, _, _) in enumerate(latest_data):
            if prev_date:
                # 计算两个日期间的差距
                date_obj = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
                prev_date_obj = datetime.strptime(str(prev_date)[:10], '%Y-%m-%d')
                gap_days = (date_obj - prev_date_obj).days
                
                if gap_days > 5:  # 如果间隔超过5个工作日（可能是周末+节假日）
                    gaps.append((prev_date, date_str, gap_days))
            
            prev_date = date_str
        
        if gaps:
            print("发现数据跳跃:")
            for prev, curr, gap in gaps[:5]:  # 只显示前5个
                print(f"  {prev} → {curr} (间隔{gap}天)")
        else:
            print("数据连续性良好")
            
    except Exception as e:
        print(f"检查过程出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_data_range()