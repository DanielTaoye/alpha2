"""从生产环境同步股票数据到本地数据库（增量同步）"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pymysql
from pymysql.cursors import DictCursor

# 添加项目路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# 尝试从配置文件加载，如果不存在则使用默认值
try:
    from scripts.sync_config import PROD_DB_CONFIG, LOCAL_DB_CONFIG
except ImportError:
    # 默认配置（需要修改）
    PROD_DB_CONFIG = {
        'host': '生产环境IP',  # 请修改为实际的生产环境IP
        'port': 3306,
        'user': '生产环境用户名',  # 请修改为实际的用户名
        'password': '生产环境密码',  # 请修改为实际的密码
        'database': 'stock',  # 数据库名
        'charset': 'utf8mb4'
    }
    
    # 本地数据库配置（从config.py读取）
    try:
        import sys
        root_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(root_dir))
        from config import DATABASE_CONFIG
        LOCAL_DB_CONFIG = DATABASE_CONFIG
    except ImportError:
        LOCAL_DB_CONFIG = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '1234',
            'database': 'stock',
            'charset': 'utf8mb4'
        }

# 周期类型映射
PERIOD_TYPE_MAP = {
    '30min': '30min',
    'day': '1day',
    'week': '1week',
    'month': '1month'
}


def load_stock_config() -> Dict[str, List[Dict]]:
    """加载股票配置文件"""
    config_path = backend_dir / 'infrastructure' / 'config' / 'stock_config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_table_names() -> List[str]:
    """获取所有股票表名"""
    config = load_stock_config()
    table_names = []
    for stocks in config.values():
        for stock in stocks:
            table_name = stock.get('table')
            if table_name and table_name not in table_names:
                table_names.append(table_name)
    return table_names


def get_local_max_time(conn, table_name: str, period_code: str) -> Optional[datetime]:
    """获取本地数据库中指定表和周期的最大时间"""
    try:
        cursor = conn.cursor(DictCursor)
        query = f"""
            SELECT MAX(shi_jian) as max_time
            FROM {table_name}
            WHERE peroid_type = %s
        """
        cursor.execute(query, (period_code,))
        result = cursor.fetchone()
        cursor.close()
        
        if result and result.get('max_time'):
            return result['max_time']
        return None
    except Exception as e:
        logger.warning(f"获取本地最大时间失败: {table_name}, {period_code}, 错误={str(e)}")
        return None


def sync_table_data(
    prod_conn,
    local_conn,
    table_name: str,
    period_type: str,
    period_code: str,
    batch_size: int = 1000
) -> int:
    """
    同步单个表的数据
    
    Args:
        prod_conn: 生产环境数据库连接
        local_conn: 本地数据库连接
        table_name: 表名
        period_type: 周期类型（用于日志）
        period_code: 周期代码（数据库中的值）
        batch_size: 批量插入大小
        
    Returns:
        同步的记录数
    """
    try:
        # 获取本地最大时间
        local_max_time = get_local_max_time(local_conn, table_name, period_code)
        
        # 构建查询条件
        if local_max_time:
            # 增量同步：只同步大于本地最大时间的数据
            start_time = local_max_time
            logger.info(f"增量同步 {table_name} {period_type}: 从 {start_time} 开始")
        else:
            # 全量同步：同步最近2年的数据
            start_time = datetime.now() - timedelta(days=730)
            logger.info(f"全量同步 {table_name} {period_type}: 从 {start_time} 开始")
        
        # 从生产环境查询数据
        prod_cursor = prod_conn.cursor(DictCursor)
        query = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
                   cheng_jiao_liang, liang_bi, wei_bi, peroid_type
            FROM {table_name}
            WHERE peroid_type = %s AND shi_jian > %s
            ORDER BY shi_jian ASC
        """
        prod_cursor.execute(query, (period_code, start_time))
        
        # 批量插入到本地数据库
        local_cursor = local_conn.cursor()
        # 使用 INSERT IGNORE 或 ON DUPLICATE KEY UPDATE
        # 假设表有基于 (shi_jian, peroid_type) 的唯一索引
        insert_query = f"""
            INSERT INTO {table_name} 
            (shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
             cheng_jiao_liang, liang_bi, wei_bi, peroid_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                kai_pan_jia = VALUES(kai_pan_jia),
                zui_gao_jia = VALUES(zui_gao_jia),
                zui_di_jia = VALUES(zui_di_jia),
                shou_pan_jia = VALUES(shou_pan_jia),
                cheng_jiao_liang = VALUES(cheng_jiao_liang),
                liang_bi = VALUES(liang_bi),
                wei_bi = VALUES(wei_bi)
        """
        
        count = 0
        batch = []
        
        while True:
            rows = prod_cursor.fetchmany(batch_size)
            if not rows:
                break
            
            for row in rows:
                batch.append((
                    row['shi_jian'],
                    row['kai_pan_jia'],
                    row['zui_gao_jia'],
                    row['zui_di_jia'],
                    row['shou_pan_jia'],
                    row['cheng_jiao_liang'],
                    row['liang_bi'],
                    row['wei_bi'],
                    row['peroid_type']
                ))
                
                if len(batch) >= batch_size:
                    local_cursor.executemany(insert_query, batch)
                    local_conn.commit()
                    count += len(batch)
                    logger.debug(f"已同步 {table_name} {period_type}: {count} 条记录")
                    batch = []
            
            if batch:
                local_cursor.executemany(insert_query, batch)
                local_conn.commit()
                count += len(batch)
                batch = []
        
        prod_cursor.close()
        local_cursor.close()
        
        if count > 0:
            logger.info(f"✅ 同步完成 {table_name} {period_type}: {count} 条新记录")
        else:
            logger.info(f"ℹ️  {table_name} {period_type}: 无新数据")
        
        return count
        
    except Exception as e:
        logger.error(f"❌ 同步失败 {table_name} {period_type}: {str(e)}", exc_info=True)
        return 0


def check_table_exists(conn, table_name: str) -> bool:
    """检查表是否存在"""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    except Exception as e:
        logger.error(f"检查表是否存在失败: {table_name}, 错误={str(e)}")
        return False


def sync_all_stocks():
    """同步所有股票数据"""
    logger.info("=" * 60)
    logger.info("开始同步股票数据（从生产环境到本地）")
    logger.info("=" * 60)
    
    # 连接数据库
    try:
        logger.info("正在连接生产环境数据库...")
        prod_conn = pymysql.connect(**PROD_DB_CONFIG)
        logger.info("✅ 生产环境数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 生产环境数据库连接失败: {str(e)}")
        return
    
    try:
        logger.info("正在连接本地数据库...")
        local_conn = pymysql.connect(**LOCAL_DB_CONFIG)
        logger.info("✅ 本地数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 本地数据库连接失败: {str(e)}")
        prod_conn.close()
        return
    
    try:
        # 获取所有表名
        table_names = get_all_table_names()
        logger.info(f"找到 {len(table_names)} 个股票表需要同步")
        
        # 支持的周期类型
        periods = ['30min', 'day', 'week', 'month']
        
        total_synced = 0
        total_tables = 0
        
        # 遍历每个表
        for table_name in table_names:
            # 检查表是否存在
            if not check_table_exists(prod_conn, table_name):
                logger.warning(f"⚠️  生产环境表不存在: {table_name}，跳过")
                continue
            
            if not check_table_exists(local_conn, table_name):
                logger.warning(f"⚠️  本地表不存在: {table_name}，跳过")
                continue
            
            logger.info(f"\n📊 开始同步表: {table_name}")
            
            # 同步每个周期
            for period_type in periods:
                period_code = PERIOD_TYPE_MAP[period_type]
                count = sync_table_data(
                    prod_conn,
                    local_conn,
                    table_name,
                    period_type,
                    period_code
                )
                total_synced += count
                if count > 0:
                    total_tables += 1
        
        logger.info("\n" + "=" * 60)
        logger.info(f"同步完成！")
        logger.info(f"共同步 {total_synced} 条记录，涉及 {total_tables} 个表/周期组合")
        logger.info("=" * 60)
        
    finally:
        prod_conn.close()
        local_conn.close()
        logger.info("数据库连接已关闭")


if __name__ == '__main__':
    # 检查配置
    if PROD_DB_CONFIG.get('host') in ['生产环境IP', '192.168.1.100'] or not PROD_DB_CONFIG.get('host'):
        print("=" * 60)
        print("⚠️  警告：请先配置生产环境数据库连接信息！")
        print("=" * 60)
        print("请创建配置文件 backend/scripts/sync_config.py")
        print("参考 sync_config_example.py 文件")
        print("=" * 60)
        sys.exit(1)
    
    print("=" * 60)
    print(f"生产环境: {PROD_DB_CONFIG['host']}:{PROD_DB_CONFIG['port']}")
    print(f"本地环境: {LOCAL_DB_CONFIG['host']}:{LOCAL_DB_CONFIG['port']}")
    print("=" * 60)
    
    sync_all_stocks()

