#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从生产环境导入股票数据到本地数据库
支持导入 basic_stock 表和对应的K线数据表
"""

import pymysql
import sys
from datetime import datetime

# 设置Windows控制台编码
if sys.platform == 'win32':
    import locale
    # 使用更安全的方式设置编码
    try:
        # Python 3.7+
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 生产环境数据库配置（腾讯云）
PROD_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 本地数据库配置
LOCAL_DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '1234',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 股票列表配置
STOCK_CONFIG = {
    '波段': [
        {'code': 'SZ300188', 'name': '国投智能'},
        {'code': 'SH603556', 'name': '海兴电力'},
        {'code': 'SZ002130', 'name': '沃尔核材'},
        {'code': 'SH600037', 'name': '歌华有线'},
        {'code': 'SZ301039', 'name': '中集车辆'},
        {'code': 'SZ300058', 'name': '蓝色光标'},
        {'code': 'SZ300768', 'name': '迪普科技'},
        {'code': 'SH688536', 'name': '思瑞浦'},
        {'code': 'SH600458', 'name': '时代新材'},
        {'code': 'SZ002065', 'name': '东华软件'},
        {'code': 'SH603327', 'name': '福蓉科技'},
        {'code': 'SZ300564', 'name': '筑博设计'},
        {'code': 'SH603298', 'name': '杭叉集团'},
        {'code': 'SZ002387', 'name': '维信诺'},
        {'code': 'SH600518', 'name': '康美药业'},
        {'code': 'SH600256', 'name': '广汇能源'},
        {'code': 'SH603486', 'name': '科沃斯'},
        {'code': 'SH603588', 'name': '高能环境'},
        {'code': 'SZ000786', 'name': '北新建材'},
        {'code': 'SH600179', 'name': '安通控股'}
    ],
    '短线': [
        {'code': 'SH600004', 'name': '白云机场'},
        {'code': 'SZ300443', 'name': '金雷股份'},
        {'code': 'SH600889', 'name': '南京化纤'},
        {'code': 'SH688512', 'name': '慧智微-U'},
        {'code': 'SH688693', 'name': '锴威特'},
        {'code': 'SH600075', 'name': '新疆天业'},
        {'code': 'SZ002722', 'name': '物产金轮'},
        {'code': 'SH688549', 'name': '中巨芯-U'},
        {'code': 'SH603319', 'name': '美湖股份'},
        {'code': 'SZ300249', 'name': '依米康'},
        {'code': 'SH600579', 'name': '中化装备'},
        {'code': 'SZ300662', 'name': '科锐国际'},
        {'code': 'SZ002857', 'name': '三晖电气'},
        {'code': 'SZ002751', 'name': '易尚退'},
        {'code': 'SZ001324', 'name': '长青科技'},
        {'code': 'SZ301191', 'name': '菲菱科思'},
        {'code': 'SZ300772', 'name': '运达股份'},
        {'code': 'SH688585', 'name': '上纬新材'},
        {'code': 'SZ301448', 'name': '开创电气'},
        {'code': 'SH688653', 'name': '康希通信'}
    ],
    '中长线': [
        {'code': 'SZ002475', 'name': '立讯精密'},
        {'code': 'SZ300750', 'name': '宁德时代'},
        {'code': 'SH601288', 'name': '农业银行'},
        {'code': 'SH601857', 'name': '中国石油'},
        {'code': 'SH601899', 'name': '紫金矿业'},
        {'code': 'SH688036', 'name': '传音控股'},
        {'code': 'SH601128', 'name': '常熟银行'},
        {'code': 'SZ000338', 'name': '潍柴动力'},
        {'code': 'SH600585', 'name': '海螺水泥'},
        {'code': 'SH600016', 'name': '民生银行'},
        {'code': 'SH600741', 'name': '华域汽车'},
        {'code': 'SZ000166', 'name': '申万宏源'},
        {'code': 'SH601225', 'name': '陕西煤业'},
        {'code': 'SZ000568', 'name': '泸州老窖'},
        {'code': 'SZ002807', 'name': '江阴银行'},
        {'code': 'SH688012', 'name': '中微公司'},
        {'code': 'SH601021', 'name': '春秋航空'},
        {'code': 'SZ002625', 'name': '光启技术'},
        {'code': 'SH600066', 'name': '宇通客车'},
        {'code': 'SH601919', 'name': '中远海控'}
    ]
}


def get_table_name(stock_code):
    """根据股票代码生成表名"""
    return f"basic_data_{stock_code.lower()}"


def connect_db(config):
    """连接数据库"""
    try:
        conn = pymysql.connect(**config)
        return conn
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return None


def check_stock_exists(conn, stock_code):
    """检查股票是否已存在于basic_stock表"""
    cursor = conn.cursor()
    query = "SELECT code FROM basic_stock WHERE code = %s"
    cursor.execute(query, (stock_code,))
    result = cursor.fetchone()
    cursor.close()
    return result is not None


def import_basic_stock(prod_conn, local_conn, stock_code, stock_name):
    """导入股票基本信息"""
    try:
        # 检查是否已存在
        if check_stock_exists(local_conn, stock_code):
            print(f"  ℹ {stock_name}({stock_code}) 已存在于basic_stock表，跳过...")
            return True
        
        # 从生产环境读取
        prod_cursor = prod_conn.cursor(pymysql.cursors.DictCursor)
        query = "SELECT * FROM basic_stock WHERE code = %s"
        prod_cursor.execute(query, (stock_code,))
        stock_data = prod_cursor.fetchone()
        prod_cursor.close()
        
        if not stock_data:
            print(f"  ✗ 生产环境未找到 {stock_name}({stock_code}) 的数据")
            return False
        
        # 导入到本地
        local_cursor = local_conn.cursor()
        
        # 构建INSERT语句
        columns = ', '.join([f"`{col}`" for col in stock_data.keys()])
        placeholders = ', '.join(['%s'] * len(stock_data))
        insert_query = f"INSERT INTO basic_stock ({columns}) VALUES ({placeholders})"
        
        local_cursor.execute(insert_query, tuple(stock_data.values()))
        local_conn.commit()
        local_cursor.close()
        
        print(f"  ✓ 成功导入 {stock_name}({stock_code}) 基本信息")
        return True
        
    except Exception as e:
        print(f"  ✗ 导入 {stock_name}({stock_code}) 基本信息失败: {e}")
        return False


def check_table_exists(conn, table_name):
    """检查表是否存在"""
    cursor = conn.cursor()
    query = f"SHOW TABLES LIKE '{table_name}'"
    cursor.execute(query)
    result = cursor.fetchone()
    cursor.close()
    return result is not None


def create_kline_table(local_conn, prod_conn, table_name):
    """从生产环境复制表结构创建K线数据表"""
    try:
        # 从生产环境获取建表语句
        prod_cursor = prod_conn.cursor()
        prod_cursor.execute(f"SHOW CREATE TABLE {table_name}")
        result = prod_cursor.fetchone()
        prod_cursor.close()
        
        if not result:
            print(f"  ✗ 无法获取表 {table_name} 的结构")
            return False
        
        # 获取CREATE TABLE语句（第二列）
        create_sql = result[1]
        
        # 替换为 CREATE TABLE IF NOT EXISTS
        create_sql = create_sql.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1)
        
        # 如果表已存在，先删除（确保结构一致）
        local_cursor = local_conn.cursor()
        try:
            # 检查表是否存在
            local_cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if local_cursor.fetchone():
                print(f"    表 {table_name} 已存在，删除旧表...")
                local_cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                local_conn.commit()
        except:
            pass
        
        # 在本地执行建表语句
        local_cursor.execute(create_sql)
        local_conn.commit()
        local_cursor.close()
        
        print(f"    表 {table_name} 创建成功")
        return True
        
    except Exception as e:
        print(f"  ✗ 创建表 {table_name} 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def import_kline_data(prod_conn, local_conn, stock_code, stock_name, table_name, batch_size=1000):
    """导入K线数据"""
    try:
        # 检查生产环境表是否存在
        if not check_table_exists(prod_conn, table_name):
            print(f"  ⚠ 生产环境表 {table_name} 不存在")
            return False
        
        # 检查本地表是否存在
        table_exists = check_table_exists(local_conn, table_name)
        
        if table_exists:
            # 检查是否已有数据
            local_cursor = local_conn.cursor()
            local_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            local_count = local_cursor.fetchone()[0]
            local_cursor.close()
            
            if local_count > 0:
                print(f"  ℹ 表 {table_name} 已有 {local_count} 条数据，跳过...")
                return True
            else:
                # 表存在但无数据，可能是之前失败的，删除重建
                print(f"  ℹ 表 {table_name} 存在但无数据，重新创建...")
        else:
            print(f"  ℹ 本地表 {table_name} 不存在，正在创建...")
        
        # 创建或重建表
        if not create_kline_table(local_conn, prod_conn, table_name):
            return False
        
        # 从生产环境读取数据
        prod_cursor = prod_conn.cursor(pymysql.cursors.DictCursor)
        query = f"SELECT * FROM {table_name} ORDER BY shi_jian ASC"
        prod_cursor.execute(query)
        
        # 批量导入
        total = 0
        batch = []
        
        print(f"  ℹ 正在导入 {table_name} 的数据...")
        
        for row in prod_cursor:
            batch.append(row)
            
            if len(batch) >= batch_size:
                # 批量插入
                if batch:
                    columns = ', '.join([f"`{col}`" for col in batch[0].keys()])
                    placeholders = ', '.join(['%s'] * len(batch[0]))
                    insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                    
                    local_cursor = local_conn.cursor()
                    for data in batch:
                        local_cursor.execute(insert_query, tuple(data.values()))
                    local_conn.commit()
                    local_cursor.close()
                    
                    total += len(batch)
                    print(f"    已导入 {total} 条数据...")
                    batch = []
        
        # 导入剩余数据
        if batch:
            columns = ', '.join([f"`{col}`" for col in batch[0].keys()])
            placeholders = ', '.join(['%s'] * len(batch[0]))
            insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            
            local_cursor = local_conn.cursor()
            for data in batch:
                local_cursor.execute(insert_query, tuple(data.values()))
            local_conn.commit()
            local_cursor.close()
            
            total += len(batch)
        
        prod_cursor.close()
        
        print(f"  ✓ 成功导入 {stock_name}({stock_code}) K线数据，共 {total} 条")
        return True
        
    except Exception as e:
        print(f"  ✗ 导入 {stock_name}({stock_code}) K线数据失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("从生产环境导入股票数据到本地数据库")
    print("=" * 70)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 连接数据库
    print("\n1. 连接数据库...")
    prod_conn = connect_db(PROD_DB_CONFIG)
    if not prod_conn:
        print("✗ 无法连接到生产环境数据库")
        return
    print("  ✓ 生产环境数据库连接成功")
    
    local_conn = connect_db(LOCAL_DB_CONFIG)
    if not local_conn:
        print("✗ 无法连接到本地数据库")
        prod_conn.close()
        return
    print("  ✓ 本地数据库连接成功")
    
    # 统计
    total_stocks = 0
    success_basic = 0
    success_kline = 0
    
    # 导入数据
    print("\n2. 开始导入股票数据...")
    print("-" * 70)
    
    for strategy_type, stocks in STOCK_CONFIG.items():
        print(f"\n【{strategy_type}策略】 - 共 {len(stocks)} 支股票")
        print("-" * 70)
        
        for stock in stocks:
            total_stocks += 1
            stock_code = stock['code']
            stock_name = stock['name']
            table_name = get_table_name(stock_code)
            
            print(f"\n处理 {stock_name}({stock_code})...")
            
            # 导入基本信息
            if import_basic_stock(prod_conn, local_conn, stock_code, stock_name):
                success_basic += 1
            
            # 导入K线数据
            if import_kline_data(prod_conn, local_conn, stock_code, stock_name, table_name):
                success_kline += 1
    
    # 关闭连接
    prod_conn.close()
    local_conn.close()
    
    # 输出统计
    print("\n" + "=" * 70)
    print("导入完成统计")
    print("=" * 70)
    print(f"总股票数: {total_stocks}")
    print(f"基本信息成功: {success_basic}/{total_stocks}")
    print(f"K线数据成功: {success_kline}/{total_stocks}")
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    if success_basic == total_stocks and success_kline == total_stocks:
        print("\n✓ 所有数据导入成功！")
    else:
        print(f"\n⚠ 部分数据导入失败，请检查日志")
    
    print("\n下一步：运行以下命令更新app.py配置")
    print("  python update_app_config.py")


if __name__ == '__main__':
    main()

