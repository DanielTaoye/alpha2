# -*- coding: utf-8 -*-
"""
检查K线数据是否完整
"""

import pymysql
import sys
from datetime import datetime, timedelta

# Windows控制台编码设置
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 测试用的表（白云机场）
TEST_TABLE = 'basic_data_sh600004'

# 周期类型
PERIOD_TYPES = {
    '1': '1分钟',
    '2': '5分钟',
    '3': '15分钟',
    '4': '30分钟',
    '5': '60分钟',
    '6': '日K线',
    '7': '周K线',
    '8': '月K线',
}

print("=" * 80)
print("检查K线数据")
print("=" * 80)
print(f"数据库: {DB_CONFIG['database']}")
print(f"测试表: {TEST_TABLE} (白云机场)")
print("=" * 80)

try:
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    # 检查表结构
    print("\n[1] 检查表结构...")
    cursor.execute(f"DESCRIBE {TEST_TABLE}")
    columns = cursor.fetchall()
    
    print("表字段:")
    for col in columns[:10]:  # 只显示前10个字段
        print(f"  - {col['Field']:20} {col['Type']:20} {col['Null']:5}")
    if len(columns) > 10:
        print(f"  ... 还有 {len(columns) - 10} 个字段")
    
    # 检查peroid_type字段的所有值
    print("\n[2] 检查周期类型...")
    cursor.execute(f"SELECT DISTINCT peroid_type FROM {TEST_TABLE} ORDER BY peroid_type")
    period_types = cursor.fetchall()
    
    print("表中存在的周期类型:")
    for pt in period_types:
        period_code = pt['peroid_type']
        period_name = PERIOD_TYPES.get(period_code, '未知')
        print(f"  - peroid_type = '{period_code}' -> {period_name}")
    
    # 检查每个周期的数据量
    print("\n[3] 检查数据量...")
    three_years_ago = datetime.now() - timedelta(days=365*3)
    
    for pt in period_types:
        period_code = pt['peroid_type']
        period_name = PERIOD_TYPES.get(period_code, '未知')
        
        # 总数据量
        cursor.execute(f"SELECT COUNT(*) as count FROM {TEST_TABLE} WHERE peroid_type = %s", (period_code,))
        total = cursor.fetchone()['count']
        
        # 最近3年数据量
        cursor.execute(f"""
            SELECT COUNT(*) as count, 
                   MIN(shi_jian) as min_time, 
                   MAX(shi_jian) as max_time
            FROM {TEST_TABLE} 
            WHERE peroid_type = %s AND shi_jian >= %s
        """, (period_code, three_years_ago))
        recent = cursor.fetchone()
        
        print(f"\n  {period_name} (peroid_type='{period_code}'):")
        print(f"    总记录数: {total}")
        print(f"    最近3年: {recent['count']} 条")
        if recent['min_time'] and recent['max_time']:
            print(f"    时间范围: {recent['min_time']} ~ {recent['max_time']}")
    
    # 检查样本数据
    print("\n[4] 检查样本数据...")
    cursor.execute(f"""
        SELECT shi_jian, peroid_type, kai_pan_jia, zui_gao_jia, 
               zui_di_jia, shou_pan_jia, cheng_jiao_liang
        FROM {TEST_TABLE}
        WHERE peroid_type = '4'
        ORDER BY shi_jian DESC
        LIMIT 3
    """)
    samples = cursor.fetchall()
    
    if samples:
        print("30分钟K线样本数据（最新3条）:")
        for s in samples:
            print(f"  时间: {s['shi_jian']}")
            print(f"    开盘: {s['kai_pan_jia']}, 收盘: {s['shou_pan_jia']}")
            print(f"    最高: {s['zui_gao_jia']}, 最低: {s['zui_di_jia']}")
            print(f"    成交量: {s['cheng_jiao_liang']}")
    else:
        print("未找到30分钟K线数据")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("检查完成！")
    print("=" * 80)
    print("\n如果看到了30分钟、日K、周K、月K的数据，说明数据正常。")
    print("现在可以重启后端服务了！")
    print("=" * 80)
    
except Exception as e:
    print(f"[错误] {e}")
    import traceback
    traceback.print_exc()

print()

