"""检查shang_yu_bi字段数据"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.persistence.database import DatabaseConnection


def check_shang_yu_bi():
    """检查shang_yu_bi字段"""
    db = DatabaseConnection()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # 查询最近20条日线数据
        query = """
        SELECT shi_jian, kai_pan_jia, shou_pan_jia, shang_yu_bi, cheng_jiao_liang
        FROM basic_data_sz300564
        WHERE peroid_type = 'day' OR (HOUR(shi_jian) = 0 AND MINUTE(shi_jian) = 0)
        ORDER BY shi_jian DESC
        LIMIT 20
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print("最近20条日线数据 (shang_yu_bi 涨跌幅%):")
        print(f"{'日期':<20} {'开盘':<10} {'收盘':<10} {'涨跌幅%':<12} {'成交量':<15}")
        print("-"*80)
        
        for row in rows:
            shi_jian, kai_pan_jia, shou_pan_jia, shang_yu_bi, cheng_jiao_liang = row
            print(f"{str(shi_jian):<20} {kai_pan_jia:<10.2f} {shou_pan_jia:<10.2f} {shang_yu_bi if shang_yu_bi else 'NULL':<12} {cheng_jiao_liang:<15}")
        
        # 统计shang_yu_bi为NULL或0的数量
        query2 = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN shang_yu_bi IS NULL THEN 1 ELSE 0 END) as null_count,
            SUM(CASE WHEN shang_yu_bi = 0 THEN 1 ELSE 0 END) as zero_count
        FROM basic_data_sz300564
        WHERE HOUR(shi_jian) = 0 AND MINUTE(shi_jian) = 0
        """
        cursor.execute(query2)
        total, null_count, zero_count = cursor.fetchone()
        
        print(f"\n统计:")
        print(f"  总日线数据: {total}条")
        print(f"  shang_yu_bi为NULL: {null_count}条 ({null_count/total*100 if total > 0 else 0:.2f}%)")
        print(f"  shang_yu_bi为0: {zero_count}条 ({zero_count/total*100 if total > 0 else 0:.2f}%)")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    check_shang_yu_bi()

