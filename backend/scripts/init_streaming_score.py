"""初始化流式微批分数表结构"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = Path(backend_dir).parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def get_master_db_connection():
    """
    获取生产主库连接（可写）
    优先使用 config_production_master.py，否则使用 config_master.py
    """
    try:
        # 尝试导入生产主库配置
        try:
            from config_production_master import DATABASE_CONFIG as MASTER_CONFIG
            logger.info("✅ 使用生产主库配置（外网）")
        except ImportError:
            try:
                from config_master import DATABASE_CONFIG as MASTER_CONFIG
                logger.info("✅ 使用主库配置（内网）")
            except ImportError:
                # 如果都没有，使用默认配置（可能是从库，会报错）
                logger.warning("⚠️ 未找到主库配置，使用默认配置（可能只读）")
                from infrastructure.config.database_config import DATABASE_CONFIG as MASTER_CONFIG
        
        return pymysql.connect(
            host=MASTER_CONFIG['host'],
            port=MASTER_CONFIG['port'],
            user=MASTER_CONFIG['user'],
            password=MASTER_CONFIG['password'],
            database=MASTER_CONFIG['database'],
            charset=MASTER_CONFIG.get('charset', 'utf8mb4'),
            autocommit=True
        )
    except Exception as e:
        logger.error(f"连接主库失败: {e}", exc_info=True)
        raise


def add_score_columns():
    """在 b_daily_chance 表中添加分数字段（使用主库）"""
    conn = None
    try:
        # 使用主库连接（可写）
        conn = get_master_db_connection()
        cursor = conn.cursor()
        
        logger.info("开始添加分数字段到 b_daily_chance 表...")
        logger.info(f"连接主库: {conn.host}:{conn.port}")
        
        # 检查字段是否已存在
        cursor.execute("SHOW COLUMNS FROM b_daily_chance LIKE 'strategy1_score'")
        if cursor.fetchone():
            logger.info("⚠️ 字段已存在，跳过创建")
            return
        
        # 添加字段
        sqls = [
            "ALTER TABLE b_daily_chance ADD COLUMN strategy1_score DECIMAL(5,2) DEFAULT NULL COMMENT '策略1实时分数'",
            "ALTER TABLE b_daily_chance ADD COLUMN strategy2_score DECIMAL(5,2) DEFAULT NULL COMMENT '策略2实时分数'",
            "ALTER TABLE b_daily_chance ADD COLUMN total_score DECIMAL(5,2) DEFAULT NULL COMMENT '总评分(最高分*1.2,最高99)'",
            "ALTER TABLE b_daily_chance ADD COLUMN is_high_score TINYINT(1) DEFAULT 0 COMMENT '是否高分股票(0=否,1=是)'",
            "ALTER TABLE b_daily_chance ADD COLUMN score_updated_at DATETIME DEFAULT NULL COMMENT '分数最后更新时间'"
        ]
        
        for sql in sqls:
            logger.info(f"执行: {sql}")
            cursor.execute(sql)
            conn.commit()
        
        # 添加索引
        index_sqls = [
            "CREATE INDEX idx_is_high_score ON b_daily_chance(is_high_score, date)",
            "CREATE INDEX idx_total_score ON b_daily_chance(total_score)",
            "CREATE INDEX idx_score_updated ON b_daily_chance(score_updated_at)"
        ]
        
        for sql in index_sqls:
            try:
                logger.info(f"创建索引: {sql}")
                cursor.execute(sql)
                conn.commit()
            except Exception as e:
                logger.warning(f"索引创建失败（可能已存在）: {e}")
        
        logger.info("✅ 分数字段添加成功！")
        
    except Exception as e:
        logger.error(f"❌ 添加字段失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("初始化流式微批分数表结构")
    print("=" * 60)
    
    try:
        add_score_columns()
        print("\n✅ 初始化完成！")
        print("\n下一步：启动Flask服务，流式微批服务会自动启动")
        print("命令: python backend/app.py")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        sys.exit(1)
