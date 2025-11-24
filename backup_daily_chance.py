"""备份 b_daily_chance 表的关键字段"""
import sys
from pathlib import Path
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
import json

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config import DATABASE_CONFIG


def backup_daily_chance():
    """备份 b_daily_chance 表"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"backup_daily_chance_{timestamp}.sql"
    
    print("=" * 80)
    print("备份 b_daily_chance 表")
    print("=" * 80)
    print(f"数据库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}")
    print(f"备份文件: {backup_file}")
    print("-" * 80)
    
    try:
        conn = pymysql.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password'],
            database=DATABASE_CONFIG['database'],
            charset=DATABASE_CONFIG['charset']
        )
        print("✓ 数据库连接成功")
        
        with conn.cursor(DictCursor) as cursor:
            # 获取记录数
            cursor.execute("SELECT COUNT(*) as cnt FROM b_daily_chance")
            total = cursor.fetchone()['cnt']
            print(f"✓ 找到 {total} 条记录")
            
            # 导出数据
            cursor.execute("""
                SELECT id, stock_code, date, volume_type, bullish_pattern, bearish_pattern
                FROM b_daily_chance
                ORDER BY stock_code, date
            """)
            records = cursor.fetchall()
            
            print("✓ 数据读取完成，正在写入备份文件...")
            
            # 写入SQL文件
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(f"-- b_daily_chance 备份文件\n")
                f.write(f"-- 备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"-- 记录数: {len(records)}\n\n")
                
                for i, record in enumerate(records, 1):
                    date_str = record['date'].strftime('%Y-%m-%d') if record['date'] else 'NULL'
                    volume_type = record['volume_type'] or ''
                    bullish = record['bullish_pattern'] or ''
                    bearish = record['bearish_pattern'] or ''
                    
                    f.write(f"UPDATE b_daily_chance SET ")
                    f.write(f"volume_type='{volume_type}', ")
                    f.write(f"bullish_pattern='{bullish}', ")
                    f.write(f"bearish_pattern='{bearish}' ")
                    f.write(f"WHERE id={record['id']};\n")
                    
                    if i % 1000 == 0:
                        print(f"  进度: {i}/{len(records)}")
            
            print(f"✓ 备份完成！")
            print(f"  文件: {backup_file}")
            print(f"  记录数: {len(records)}")
            
            # 恢复说明
            print("\n" + "=" * 80)
            print("恢复方法：")
            print("=" * 80)
            print(f"mysql -h {DATABASE_CONFIG['host']} -u {DATABASE_CONFIG['user']} -p {DATABASE_CONFIG['database']} < {backup_file}")
            print("=" * 80)
        
        conn.close()
        
    except Exception as e:
        print(f"✗ 备份失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    backup_daily_chance()

