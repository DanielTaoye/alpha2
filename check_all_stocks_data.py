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

def check_multiple_stocks():
    """检查多个股票的数据时间范围"""
    test_stocks = [
        "SH600000",  # 浦发银行
        "SH600036",  # 招商银行  
        "SZ000001",  # 平安银行
        "SZ301039"   # 中集车辆
    ]
    
    conn = connect_database()
    cursor = conn.cursor()
    
    print("=== 检查多个股票数据时间范围 ===")
    
    for stock_code in test_stocks:
        table_name = f"basic_data_{stock_code.lower()}"
        
        print(f"\n--- {stock_code} ---")
        
        try:
            # 检查表是否存在
            check_table_sql = f"SHOW TABLES LIKE '{table_name}'"
            cursor.execute(check_table_sql)
            table_exists = cursor.fetchone()
            
            if not table_exists:
                print(f"❌ 表 {table_name} 不存在")
                continue
            
            # 检查数据时间范围
            range_sql = f"""
            SELECT 
                MIN(DATE(shi_jian)) as earliest_date,
                MAX(DATE(shi_jian)) as latest_date,
                COUNT(*) as total_records
            FROM {table_name}
            WHERE peroid_type = '1day'
            """
            cursor.execute(range_sql)
            result = cursor.fetchone()
            
            if result:
                earliest, latest, total = result
                print(f"时间范围: {earliest} 至 {latest}")
                print(f"总记录数: {total}")
                
                # 检查是否有2024年数据
                recent_2024_sql = f"""
                SELECT COUNT(*) as count_2024
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) >= '2024-01-01'
                  AND DATE(shi_jian) <= '2024-12-31'
                """
                cursor.execute(recent_2024_sql)
                count_2024 = cursor.fetchone()[0]
                print(f"2024年记录数: {count_2024}")
                
                # 检查是否有2025年数据（应该是0）
                future_2025_sql = f"""
                SELECT COUNT(*) as count_2025
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) >= '2025-01-01'
                """
                cursor.execute(future_2025_sql)
                count_2025 = cursor.fetchone()[0]
                print(f"2025年记录数: {count_2025} {'❌ 发现未来数据！' if count_2025 > 0 else '✅ 正常'}")
                
                # 检查最近几条数据
                latest_sql = f"""
                SELECT DATE(shi_jian) as date, shou_pan_jia
                FROM {table_name}
                WHERE peroid_type = '1day'
                ORDER BY DATE(shi_jian) DESC
                LIMIT 5
                """
                cursor.execute(latest_sql)
                latest_data = cursor.fetchall()
                
                print("最近5条数据:")
                for date_str, close_p in latest_data:
                    print(f"  {date_str}: 收盘{close_p}")
                
            else:
                print("❌ 无法获取数据范围信息")
                
        except Exception as e:
            print(f"❌ 检查失败: {e}")
    
    cursor.close()
    conn.close()

def find_2024_10_08_data():
    """查找2024-10-08的实际正确数据"""
    test_stocks = [
        "SH600000",  # 浦发银行
        "SH600036",  # 招商银行  
        "SZ000001",  # 平安银行
        "SZ301039"   # 中集车辆
    ]
    
    conn = connect_database()
    cursor = conn.cursor()
    
    print("\n=== 查找2024-10-08的正确交易数据 ===")
    
    for stock_code in test_stocks:
        table_name = f"basic_data_{stock_code.lower()}"
        
        print(f"\n--- {stock_code} 2024-10-08数据 ---")
        
        try:
            # 查找2024-10-08的数据
            target_date_sql = f"""
            SELECT DATE(shi_jian) as date, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang
            FROM {table_name}
            WHERE peroid_type = '1day'
              AND DATE(shi_jian) = '2024-10-08'
            """
            cursor.execute(target_date_sql)
            target_data = cursor.fetchone()
            
            if target_data:
                date_str, open_p, high_p, low_p, close_p, volume = target_data
                print(f"✅ 找到2024-10-08数据:")
                print(f"  开盘: {open_p}, 最高: {high_p}, 最低: {low_p}, 收盘: {close_p}")
                print(f"  成交量: {volume}")
            else:
                print(f"❌ 未找到2024-10-08数据")
                
                # 查找10月份的数据
                october_sql = f"""
                SELECT DATE(shi_jian) as date, shou_pan_jia
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) >= '2024-10-01'
                  AND DATE(shi_jian) <= '2024-10-31'
                ORDER BY DATE(shi_jian)
                """
                cursor.execute(october_sql)
                october_data = cursor.fetchall()
                
                if october_data:
                    print("2024年10月数据:")
                    for date_str, close_p in october_data:
                        print(f"  {date_str}: 收盘{close_p}")
                else:
                    print("❌ 整个10月都没有数据")
                
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_multiple_stocks()
    find_2024_10_08_data()