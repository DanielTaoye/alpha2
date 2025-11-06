"""
数据库检查脚本
用于验证数据库连接和表结构
"""

import pymysql
from datetime import datetime, timedelta

# 数据库配置（腾讯云数据库）
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',  # 请修改为实际数据库名
    'charset': 'utf8mb4'
}

# 需要检查的表
REQUIRED_TABLES = [
    'basic_data_sz300188',  # 国投智能
    'basic_data_sh603556',  # 海兴电力
    'basic_data_sz002130',  # 沃尔核材
    'basic_data_sh600037',  # 歌华有线
    'basic_data_sz301039',  # 中集车辆
    'basic_data_sh600004',  # 白云机场
    'basic_data_sz300443',  # 金雷股份
    'basic_data_sh600889',  # 南京化纤
    'basic_data_sh688512',  # 慧智微-U
    'basic_data_sh688693',  # 锴威特
    'basic_data_sz002475',  # 立讯精密
    'basic_data_sz300750',  # 宁德时代
    'basic_data_sh601288',  # 农业银行
    'basic_data_sh601857',  # 中国石油
    'basic_data_sh601899',  # 紫金矿业
]

# 周期类型
PERIOD_TYPES = {
    '4': '30分钟',
    '6': '日K线',
    '7': '周K线',
    '8': '月K线'
}


def check_database_connection():
    """检查数据库连接"""
    print("=" * 60)
    print("正在检查数据库连接...")
    print("=" * 60)
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        print("✓ 数据库连接成功！")
        print(f"  数据库: {DB_CONFIG['database']}")
        print(f"  主机: {DB_CONFIG['host']}")
        return conn
    except Exception as e:
        print(f"✗ 数据库连接失败：{e}")
        return None


def check_tables(conn):
    """检查表是否存在"""
    print("\n" + "=" * 60)
    print("正在检查数据表...")
    print("=" * 60)
    
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SHOW TABLES")
    existing_tables = [table[0] for table in cursor.fetchall()]
    
    missing_tables = []
    existing_count = 0
    
    for table in REQUIRED_TABLES:
        if table in existing_tables:
            print(f"✓ {table}")
            existing_count += 1
        else:
            print(f"✗ {table} - 表不存在")
            missing_tables.append(table)
    
    print(f"\n统计: {existing_count}/{len(REQUIRED_TABLES)} 个表存在")
    
    if missing_tables:
        print(f"\n缺失的表：")
        for table in missing_tables:
            print(f"  - {table}")
    
    cursor.close()
    return len(missing_tables) == 0


def check_table_data(conn, sample_table='basic_data_sh600004'):
    """检查表数据"""
    print("\n" + "=" * 60)
    print(f"正在检查表数据（示例表: {sample_table}）...")
    print("=" * 60)
    
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 检查每个周期的数据
        three_years_ago = datetime.now() - timedelta(days=365*3)
        
        for period_code, period_name in PERIOD_TYPES.items():
            query = f"""
                SELECT COUNT(*) as count, 
                       MIN(shi_jian) as min_time, 
                       MAX(shi_jian) as max_time
                FROM {sample_table}
                WHERE peroid_type = %s
            """
            cursor.execute(query, (period_code,))
            result = cursor.fetchone()
            
            count = result['count']
            min_time = result['min_time']
            max_time = result['max_time']
            
            if count > 0:
                # 检查是否有3年数据
                if min_time and min_time <= three_years_ago:
                    status = "✓"
                    note = ""
                else:
                    status = "⚠"
                    note = " (数据不足3年)"
                
                print(f"{status} {period_name}: {count}条记录")
                print(f"   时间范围: {min_time} 至 {max_time}{note}")
            else:
                print(f"✗ {period_name}: 无数据")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"✗ 数据检查失败：{e}")
        cursor.close()
        return False


def check_table_structure(conn, sample_table='basic_data_sh600004'):
    """检查表结构"""
    print("\n" + "=" * 60)
    print(f"正在检查表结构（示例表: {sample_table}）...")
    print("=" * 60)
    
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"DESCRIBE {sample_table}")
        columns = cursor.fetchall()
        
        # 必需的字段
        required_fields = [
            'shi_jian', 'kai_pan_jia', 'zui_gao_jia', 
            'zui_di_jia', 'shou_pan_jia', 'cheng_jiao_liang',
            'peroid_type', 'liang_bi', 'wei_bi'
        ]
        
        existing_fields = [col[0] for col in columns]
        
        all_exist = True
        for field in required_fields:
            if field in existing_fields:
                print(f"✓ {field}")
            else:
                print(f"✗ {field} - 字段缺失")
                all_exist = False
        
        cursor.close()
        return all_exist
        
    except Exception as e:
        print(f"✗ 表结构检查失败：{e}")
        cursor.close()
        return False


def main():
    """主函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "数据库检查工具" + " " * 15 + "║")
    print("║" + " " * 12 + "阿尔法策略2.0系统" + " " * 12 + "║")
    print("╚" + "═" * 58 + "╝")
    print("\n")
    
    # 1. 检查数据库连接
    conn = check_database_connection()
    if not conn:
        print("\n请检查数据库配置后重试")
        return
    
    try:
        # 2. 检查表是否存在
        tables_ok = check_tables(conn)
        
        # 3. 检查表结构
        structure_ok = check_table_structure(conn)
        
        # 4. 检查表数据
        data_ok = check_table_data(conn)
        
        # 总结
        print("\n" + "=" * 60)
        print("检查总结")
        print("=" * 60)
        
        if tables_ok and structure_ok and data_ok:
            print("✓ 所有检查通过！系统可以正常运行。")
        else:
            print("⚠ 发现问题，请根据上述信息进行修复。")
            
            if not tables_ok:
                print("  - 部分数据表缺失")
            if not structure_ok:
                print("  - 表结构不完整")
            if not data_ok:
                print("  - 数据存在问题")
        
        print("=" * 60)
        
    finally:
        conn.close()
        print("\n数据库连接已关闭")


if __name__ == '__main__':
    main()

