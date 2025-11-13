"""
清除旧的C点数据
"""
import sys
import os

# 添加项目根目录到Python路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def main():
    """清除旧的C点数据"""
    logger.info("=" * 60)
    logger.info("开始清除旧的C点数据")
    logger.info("=" * 60)
    
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            
            # 删除所有C点数据
            sql = "DELETE FROM cr_points WHERE point_type = 'C'"
            cursor.execute(sql)
            deleted_count = cursor.rowcount
            
            logger.info(f"成功删除 {deleted_count} 条C点记录")
            
    except Exception as e:
        logger.error(f"清除C点数据失败: {e}", exc_info=True)
        return False
    
    logger.info("=" * 60)
    logger.info("清除完成！")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

