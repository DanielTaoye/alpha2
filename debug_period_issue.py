#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断30分钟和月线数据问题
"""

import pymysql
import sys
from datetime import datetime, timedelta

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

# 周期映射
PERIOD_TYPE_MAP = {
    '30min': '30min',
    'day': '1day',
    'week': 'week',
    'month': 'month'
}

def test_period(table_name, period_type, period_code):
    """测试特定周期的数据"""
    try:
        conn = pymysql.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        # 设置时间范围
        time_ranges = {
            '30min': 90,
            'day': 730,
            'week': 1095,
            'month': 1825
        }
        days = time_ranges.get(period_type, 730)
        start_date = datetime.now() - timedelta(days=days)
        
        print(f"\n{'='*70}")
        print(f"测试 {period_type} ({period_code})")
        print(f"{'='*70}")
        print(f"表名: {table_name}")
        print(f"周期代码: {period_code}")
        print(f"开始日期: {start_date.strftime('%Y-%m-%d')}")
        
        # 查询SQL（与后端一致）
        query = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                   cheng_jiao_liang, liang_bi, wei_bi
            FROM {table_name}
            WHERE peroid_type = %s AND shi_jian >= %s
            ORDER BY shi_jian DESC
            LIMIT 2000
        """
        
        print(f"\nSQL查询:")
        print(f"  WHERE peroid_type = '{period_code}' AND shi_jian >= '{start_date.strftime('%Y-%m-%d')}'")
        
        cursor.execute(query, (period_code, start_date))
        results = cursor.fetchall()
        
        print(f"\n结果:")
        print(f"  查询到 {len(results)} 条数据")
        
        if len(results) > 0:
            print(f"\n前3条数据:")
            for i, row in enumerate(results[:3], 1):
                print(f"  {i}. 时间: {row[0]}, 开盘: {row[1]}, 收盘: {row[4]}")
            print(f"  ...")
            print(f"  最新: 时间: {results[0][0]}, 开盘: {results[0][1]}, 收盘: {results[0][4]}")
        else:
            print("  ⚠️ 没有查询到数据！")
            
            # 检查是否是周期类型不对
            cursor.execute(f"SELECT DISTINCT peroid_type FROM {table_name}")
            available_types = cursor.fetchall()
            print(f"\n  表中可用的周期类型:")
            for pt in available_types:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE peroid_type = %s", (pt[0],))
                count = cursor.fetchone()[0]
                print(f"    - '{pt[0]}': {count} 条")
        
        cursor.close()
        conn.close()
        
        return len(results)
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 0


def main():
    print("="*70)
    print("诊断30分钟和月线数据问题")
    print("="*70)
    
    # 测试几只股票
    test_stocks = [
        ('basic_data_sz300188', '国投智能'),
        ('basic_data_sh600004', '白云机场'),
        ('basic_data_sz002475', '立讯精密'),
    ]
    
    for table, name in test_stocks:
        print(f"\n\n{'#'*70}")
        print(f"# 股票: {name} ({table})")
        print(f"{'#'*70}")
        
        # 测试所有周期
        for period_type, period_code in PERIOD_TYPE_MAP.items():
            count = test_period(table, period_type, period_code)
            
            if count == 0:
                print(f"  ❌ {period_type} 无数据")
            else:
                print(f"  ✅ {period_type} 有 {count} 条数据")
    
    print("\n\n" + "="*70)
    print("诊断完成")
    print("="*70)


if __name__ == '__main__':
    main()

