# -*- coding: utf-8 -*-
"""
查找15支股票的数据表
"""

import pymysql
import sys

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

# 15支股票代码
STOCK_CODES = {
    '波段策略': [
        ('国投智能', 'SZ300188', 'sz300188'),
        ('海兴电力', 'SH603556', 'sh603556'),
        ('沃尔核材', 'SZ002130', 'sz002130'),
        ('歌华有线', 'SH600037', 'sh600037'),
        ('中集车辆', 'SZ301039', 'sz301039'),
    ],
    '短线策略': [
        ('白云机场', 'SH600004', 'sh600004'),
        ('金雷股份', 'SZ300443', 'sz300443'),
        ('南京化纤', 'SH600889', 'sh600889'),
        ('慧智微-U', 'SH688512', 'sh688512'),
        ('锴威特', 'SH688693', 'sh688693'),
    ],
    '中长线策略': [
        ('立讯精密', 'SZ002475', 'sz002475'),
        ('宁德时代', 'SZ300750', 'sz300750'),
        ('农业银行', 'SH601288', 'sh601288'),
        ('中国石油', 'SH601857', 'sh601857'),
        ('紫金矿业', 'SH601899', 'sh601899'),
    ]
}

print("=" * 80)
print("查找15支股票的数据表")
print("=" * 80)
print(f"数据库: {DB_CONFIG['database']}")
print("=" * 80)

try:
    # 连接数据库
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SHOW TABLES")
    all_tables = [table[0] for table in cursor.fetchall()]
    
    print(f"\n数据库中共有 {len(all_tables)} 张表")
    
    # 查找匹配的表
    found_tables = {}
    missing_tables = {}
    
    for group_name, stocks in STOCK_CODES.items():
        print(f"\n{'=' * 80}")
        print(f"{group_name}")
        print('-' * 80)
        
        for name, code, code_lower in stocks:
            # 尝试多种可能的表名格式
            possible_names = [
                f'basic_data_{code_lower}',  # basic_data_sh600004
                f'basic_data_{code}',        # basic_data_SH600004
                f'{code_lower}',             # sh600004
                code_lower,                  # sz300188
            ]
            
            found = False
            for table_name in possible_names:
                if table_name in all_tables:
                    print(f"[找到] {name:12} {code:10} -> {table_name}")
                    if group_name not in found_tables:
                        found_tables[group_name] = []
                    found_tables[group_name].append({
                        'name': name,
                        'code': code,
                        'table': table_name
                    })
                    found = True
                    break
            
            if not found:
                print(f"[缺失] {name:12} {code:10} -> 未找到匹配的表")
                if group_name not in missing_tables:
                    missing_tables[group_name] = []
                missing_tables[group_name].append({
                    'name': name,
                    'code': code,
                    'tried': possible_names
                })
    
    # 统计结果
    total_found = sum(len(tables) for tables in found_tables.values())
    total_missing = sum(len(tables) for tables in missing_tables.values())
    
    print("\n" + "=" * 80)
    print("统计结果")
    print("=" * 80)
    print(f"找到的表: {total_found}/15")
    print(f"缺失的表: {total_missing}/15")
    
    # 如果有缺失的表，显示详细信息
    if missing_tables:
        print("\n" + "=" * 80)
        print("缺失的表详情")
        print("=" * 80)
        for group_name, stocks in missing_tables.items():
            print(f"\n{group_name}:")
            for stock in stocks:
                print(f"  {stock['name']} ({stock['code']})")
                print(f"    尝试过的表名: {', '.join(stock['tried'])}")
    
    # 显示所有包含stock相关的表（帮助用户找到正确格式）
    print("\n" + "=" * 80)
    print("数据库中包含股票代码的表（前50个）")
    print("=" * 80)
    stock_related_tables = [t for t in all_tables if any(code.lower() in t.lower() for _, _, code in 
                           [item for group in STOCK_CODES.values() for item in group])]
    
    if stock_related_tables:
        for i, table in enumerate(stock_related_tables[:50], 1):
            print(f"{i:3}. {table}")
    else:
        print("未找到相关的表")
        print("\n显示数据库中所有表（前100个）:")
        for i, table in enumerate(all_tables[:100], 1):
            print(f"{i:3}. {table}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    
except Exception as e:
    print(f"[错误] {e}")
    import traceback
    traceback.print_exc()

print()

