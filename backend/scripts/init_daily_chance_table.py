"""初始化每日机会数据表"""
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection


def init_daily_chance_table():
    """创建每日机会数据表"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS `daily_chance` (
      `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
      `stock_code` VARCHAR(20) NOT NULL COMMENT '股票代码',
      `stock_name` VARCHAR(100) NOT NULL COMMENT '股票名称',
      `stock_nature` VARCHAR(20) NOT NULL COMMENT '股性（波段、短线、中长线）',
      `date` DATE NOT NULL COMMENT '日期',
      `chance` DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '机会概率',
      `day_win_ratio_score` DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '日线赔率得分',
      `week_win_ratio_score` DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '周线赔率得分',
      `total_win_ratio_score` DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '赔率总分',
      `support_price` DECIMAL(10, 2) NULL COMMENT '支撑价格',
      `pressure_price` DECIMAL(10, 2) NULL COMMENT '压力价格',
      `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      UNIQUE KEY `uk_stock_date` (`stock_code`, `date`) COMMENT '股票代码和日期的唯一索引',
      KEY `idx_stock_code` (`stock_code`) COMMENT '股票代码索引',
      KEY `idx_date` (`date`) COMMENT '日期索引',
      KEY `idx_stock_nature` (`stock_nature`) COMMENT '股性索引'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日机会数据表'
    """
    
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            print("每日机会数据表创建成功")
            return True
    except Exception as e:
        print(f"每日机会数据表创建失败: {e}")
        return False


if __name__ == '__main__':
    print("开始初始化每日机会数据表...")
    if init_daily_chance_table():
        print("初始化完成！")
    else:
        print("初始化失败！")
        sys.exit(1)

