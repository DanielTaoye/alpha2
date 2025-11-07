#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查数据库中实际的周期类型字段值
"""

import pymysql
import sys

# 设置Windows控制台编码
if sys.platform == 'win32':
    import locale
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 导入配置
from config import DATABASE_CONFIG

def check_period_types():
    """检查数据库中的周期类型"""
    try:
        conn = pymysql.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        # 测试几个表
        test_tables = [
            'basic_data_sz300188',  # 波段
            'basic_data_sh600004',  # 短线
            'basic_data_sz002475',  # 中长线
        ]
        
        print("=" * 70)
        print("检查数据库中的周期类型字段值")
        print("=" * 70)
        
        for table in test_tables:
            print(f"\n表名: {table}")
            print("-" * 70)
            
            try:
                # 查询该表中所有不同的peroid_type值
                query = f"""
                    SELECT DISTINCT peroid_type, COUNT(*) as count 
                    FROM {table} 
                    GROUP BY peroid_type 
                    ORDER BY peroid_type
                """
                cursor.execute(query)
                results = cursor.fetchall()
                
                if results:
                    print(f"{'周期类型值':<15} {'数据条数':<10}")
                    print("-" * 70)
                    for row in results:
                        period_type = row[0] if row[0] else 'NULL'
                        count = row[1]
                        print(f"{period_type:<15} {count:<10}")
                else:
                    print("  该表没有数据")
                    
            except Exception as e:
                print(f"  查询失败: {e}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 70)
        print("说明：")
        print("  通常的周期类型值为：")
        print("  - 4 或 '4' : 30分钟K线")
        print("  - 6 或 '6' : 日K线")
        print("  - 7 或 '7' : 周K线")
        print("  - 8 或 '8' : 月K线")
        print("=" * 70)
        
    except Exception as e:
        print(f"✗ 连接数据库失败: {e}")

if __name__ == '__main__':
    check_period_types()

