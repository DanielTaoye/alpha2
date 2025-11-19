"""检查数据库中的30分钟K线数据"""
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection
import pymysql


def check_30min_data(stock_code):
    """检查指定股票的30分钟K线数据"""
    table_name = f"basic_stock_{stock_code}"
    
    conn = None
    try:
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        print(f"\n{'='*60}")
        print(f"检查表: {table_name}")
        print(f"{'='*60}\n")
        
        # 1. 检查表是否存在
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            print(f"[X] 表 {table_name} 不存在")
            return
        print(f"[OK] 表 {table_name} 存在")
        
        # 2. 检查所有周期类型
        cursor.execute(f"""
            SELECT peroid_type, COUNT(*) as count 
            FROM {table_name} 
            GROUP BY peroid_type 
            ORDER BY peroid_type
        """)
        
        print(f"\n周期类型统计:")
        print(f"-" * 40)
        period_map = {
            '30min': '30分钟K线',
            '1day': '日K线',
            'week': '周K线',
            'month': '月K线'
        }
        
        has_30min = False
        for row in cursor.fetchall():
            period_type = row['peroid_type']
            count = row['count']
            period_name = period_map.get(period_type, f'未知类型{period_type}')
            print(f"  peroid_type={period_type} ({period_name}): {count}条")
            if period_type == '30min':
                has_30min = True
        
        # 3. 如果有30分钟数据，显示前几条
        if has_30min:
            print(f"\n[OK] 该股票有30分钟K线数据")
            print(f"\n30分钟K线样例数据（最新5条）:")
            print(f"-" * 40)
            
            cursor.execute(f"""
                SELECT shi_jian, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia, peroid_type
                FROM {table_name}
                WHERE peroid_type = '30min'
                ORDER BY shi_jian DESC
                LIMIT 5
            """)
            
            for row in cursor.fetchall():
                print(f"  {row['shi_jian']}: 开={row['kai_pan_jia']}, 收={row['shou_pan_jia']}, "
                      f"高={row['zui_gao_jia']}, 低={row['zui_di_jia']}, type={row['peroid_type']}")
            
            # 4. 检查日期范围
            cursor.execute(f"""
                SELECT MIN(shi_jian) as min_date, MAX(shi_jian) as max_date
                FROM {table_name}
                WHERE peroid_type = '30min'
            """)
            date_range = cursor.fetchone()
            print(f"\n30分钟K线日期范围:")
            print(f"  最早: {date_range['min_date']}")
            print(f"  最新: {date_range['max_date']}")
            
        else:
            print(f"\n[X] 该股票没有30分钟K线数据（peroid_type='30min'）")
            print(f"    回测功能需要30分钟K线数据来计算买卖价格")
        
        print(f"\n{'='*60}\n")
        
    except Exception as e:
        print(f"[ERROR] 检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            cursor.close()
            conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python check_30min_data.py <股票代码>")
        print("例如: python check_30min_data.py 600000")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    check_30min_data(stock_code)

