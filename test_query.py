#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'backend')

try:
    from infrastructure.persistence.database import Database
    
    db = Database()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT stock_code, stock_name 
        FROM basic_stock 
        WHERE stock_name LIKE '%中集车辆%'
    """)
    
    result = cursor.fetchone()
    
    with open('query_result.txt', 'w', encoding='utf-8') as f:
        if result:
            f.write(f"找到股票: {result[0]} - {result[1]}\n")
            stock_code = result[0]
            
            # 查询2024-10-08的数据
            cursor.execute(f"""
                SELECT * FROM {stock_code}_daily 
                WHERE date = '2024-10-08'
            """)
            
            daily_data = cursor.fetchone()
            if daily_data:
                f.write(f"\n当天K线数据:\n{daily_data}\n")
            else:
                f.write("\n未找到当天K线数据\n")
            
            # 查询daily_chance
            cursor.execute(f"""
                SELECT * FROM daily_chance 
                WHERE stock_code = '{stock_code}' AND date = '2024-10-08'
            """)
            
            chance_data = cursor.fetchone()
            if chance_data:
                f.write(f"\n当天daily_chance数据:\n{chance_data}\n")
            else:
                f.write("\n未找到当天daily_chance数据\n")
        else:
            f.write("未找到中集车辆\n")
    
    conn.close()
    print("查询完成，结果保存到 query_result.txt")
    
except Exception as e:
    with open('query_result.txt', 'w', encoding='utf-8') as f:
        f.write(f"错误: {e}\n")
        import traceback
        f.write(traceback.format_exc())
    print(f"发生错误: {e}")




