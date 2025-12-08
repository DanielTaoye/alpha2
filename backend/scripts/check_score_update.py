"""检查分数更新情况 - 调试脚本"""
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = Path(backend_dir).parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def get_master_db_connection():
    """获取生产主库连接"""
    try:
        try:
            from config_production_master import DATABASE_CONFIG as MASTER_CONFIG
        except ImportError:
            try:
                from config_master import DATABASE_CONFIG as MASTER_CONFIG
            except ImportError:
                from infrastructure.config.database_config import DATABASE_CONFIG as MASTER_CONFIG
        
        return pymysql.connect(
            host=MASTER_CONFIG['host'],
            port=MASTER_CONFIG['port'],
            user=MASTER_CONFIG['user'],
            password=MASTER_CONFIG['password'],
            database=MASTER_CONFIG['database'],
            charset=MASTER_CONFIG.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        logger.error(f"连接主库失败: {e}", exc_info=True)
        raise


def check_score_updates():
    """检查分数更新情况"""
    print("=" * 70)
    print("检查分数更新情况")
    print("=" * 70)
    print()
    
    conn = None
    try:
        conn = get_master_db_connection()
        cursor = conn.cursor()
        
        # 1. 检查今天有分数的记录数
        today = datetime.now().strftime('%Y-%m-%d')
        sql1 = """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN strategy1_score IS NOT NULL THEN 1 ELSE 0 END) as has_strategy1,
                SUM(CASE WHEN strategy2_score IS NOT NULL THEN 1 ELSE 0 END) as has_strategy2,
                SUM(CASE WHEN total_score IS NOT NULL THEN 1 ELSE 0 END) as has_total,
                SUM(CASE WHEN is_high_score = 1 THEN 1 ELSE 0 END) as high_score_count,
                MAX(score_updated_at) as last_update
            FROM b_daily_chance
            WHERE date = %s
        """
        cursor.execute(sql1, (today,))
        result1 = cursor.fetchone()
        
        print(f"📊 今天 ({today}) 的数据统计:")
        print(f"   总记录数: {result1['total']}")
        print(f"   有策略1分数: {result1['has_strategy1']}")
        print(f"   有策略2分数: {result1['has_strategy2']}")
        print(f"   有总分数: {result1['has_total']}")
        print(f"   高分股票: {result1['high_score_count']}")
        print(f"   最后更新: {result1['last_update']}")
        print()
        
        # 2. 检查最近更新的10条记录
        sql2 = """
            SELECT 
                stock_code,
                stock_name,
                date,
                strategy1_score,
                strategy2_score,
                total_score,
                is_high_score,
                score_updated_at
            FROM b_daily_chance
            WHERE score_updated_at IS NOT NULL
            ORDER BY score_updated_at DESC
            LIMIT 10
        """
        cursor.execute(sql2)
        results2 = cursor.fetchall()
        
        print("📝 最近更新的10条记录:")
        print("-" * 70)
        for i, row in enumerate(results2, 1):
            print(f"{i}. {row['stock_code']} {row['stock_name']} | "
                  f"日期: {row['date']} | "
                  f"策略1: {row['strategy1_score']} | "
                  f"策略2: {row['strategy2_score']} | "
                  f"总分: {row['total_score']} | "
                  f"高分: {row['is_high_score']} | "
                  f"更新: {row['score_updated_at']}")
        print()
        
        # 3. 检查今天有数据但没有分数的记录
        sql3 = """
            SELECT 
                stock_code,
                stock_name,
                date,
                score_updated_at
            FROM b_daily_chance
            WHERE date = %s
              AND (strategy1_score IS NULL OR strategy2_score IS NULL)
            LIMIT 10
        """
        cursor.execute(sql3, (today,))
        results3 = cursor.fetchall()
        
        if results3:
            print(f"⚠️  今天有数据但没有分数的记录（前10条）:")
            print("-" * 70)
            for i, row in enumerate(results3, 1):
                print(f"{i}. {row['stock_code']} {row['stock_name']} | "
                      f"日期: {row['date']} | "
                      f"更新: {row['score_updated_at']}")
            print()
        else:
            print("✅ 今天所有记录都有分数")
            print()
        
        # 4. 检查日期格式
        sql4 = """
            SELECT 
                stock_code,
                date,
                DATE_FORMAT(date, '%%Y-%%m-%%d') as date_formatted
            FROM b_daily_chance
            WHERE date = %s
            LIMIT 5
        """
        cursor.execute(sql4, (today,))
        results4 = cursor.fetchall()
        
        print("📅 日期格式检查（前5条）:")
        print("-" * 70)
        for i, row in enumerate(results4, 1):
            print(f"{i}. {row['stock_code']} | "
                  f"原始: {row['date']} | "
                  f"格式化: {row['date_formatted']}")
        print()
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    check_score_updates()
