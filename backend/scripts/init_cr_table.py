"""初始化CR点数据表"""
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.database import DatabaseConnection


def init_cr_points_table():
    """创建CR点数据表"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS `cr_points` (
      `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
      `stock_code` VARCHAR(20) NOT NULL COMMENT '股票代码',
      `stock_name` VARCHAR(50) NOT NULL COMMENT '股票名称',
      `point_type` CHAR(1) NOT NULL COMMENT 'C或R，C表示买入点，R表示卖出点',
      `trigger_date` DATE NOT NULL COMMENT '触发日期',
      `trigger_price` DECIMAL(10, 3) NOT NULL COMMENT '触发价格',
      `open_price` DECIMAL(10, 3) NOT NULL COMMENT '开盘价',
      `high_price` DECIMAL(10, 3) NOT NULL COMMENT '最高价',
      `low_price` DECIMAL(10, 3) NOT NULL COMMENT '最低价',
      `close_price` DECIMAL(10, 3) NOT NULL COMMENT '收盘价',
      `volume` BIGINT NOT NULL COMMENT '成交量',
      `a_value` DECIMAL(10, 4) NOT NULL COMMENT 'A值-上引线',
      `b_value` DECIMAL(10, 4) NOT NULL COMMENT 'B值-实体',
      `c_value` DECIMAL(10, 4) NOT NULL COMMENT 'C值-下引线',
      `score` DECIMAL(10, 4) NOT NULL DEFAULT 0 COMMENT '策略得分',
      `strategy_name` VARCHAR(100) NOT NULL COMMENT '触发的策略名称',
      `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      INDEX `idx_stock_code` (`stock_code`),
      INDEX `idx_trigger_date` (`trigger_date`),
      INDEX `idx_point_type` (`point_type`),
      UNIQUE KEY `uk_stock_date_type` (`stock_code`, `trigger_date`, `point_type`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='CR点数据表'
    """
    
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            print("CR点数据表创建成功")
            return True
    except Exception as e:
        print(f"CR点数据表创建失败: {e}")
        return False


if __name__ == '__main__':
    print("开始初始化CR点数据表...")
    if init_cr_points_table():
        print("初始化完成！")
    else:
        print("初始化失败！")
        sys.exit(1)

