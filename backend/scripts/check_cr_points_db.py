"""
检查cr_points表中的数据
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection

try:
    with DatabaseConnection.get_connection_context() as conn:
        cursor = conn.cursor()
        
        # 查询C点数据
        sql = """
            SELECT stock_code, trigger_date, point_type, score, strategy_name 
            FROM cr_points 
            WHERE point_type = 'C'
            ORDER BY trigger_date DESC 
            LIMIT 20
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        
        print("=" * 80)
        print(f"cr_points table - Total C points: {len(results)}")
        print("=" * 80)
        
        if results:
            print(f"\n{'Stock Code':<12} {'Date':<12} {'Type':<6} {'Score':<10} {'Strategy':<30}")
            print("-" * 80)
            for row in results:
                stock_code = row[0]
                trigger_date = row[1]
                point_type = row[2]
                score = row[3]
                strategy_name = row[4]
                print(f"{stock_code:<12} {str(trigger_date):<12} {point_type:<6} {score:<10.2f} {strategy_name:<30}")
        else:
            print("\n[WARNING] No C points found in cr_points table!")
            print("This means the real-time calculation is NOT saving data to database.")
            
except Exception as e:
    print(f"Error: {e}")

