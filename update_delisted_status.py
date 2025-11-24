#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
更新all_stock表的是否退市状态
标准：如果股票的basic_stock_股票代码表中最新K线数据早于2025年11月1日，则标记为退市
"""

import pymysql
from datetime import datetime
import logging
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'connect_timeout': 30,
    'read_timeout': 30,
    'write_timeout': 30,
    'autocommit': False
}

# 退市判断日期
DELISTED_DATE = datetime(2025, 11, 1)


def get_connection(retry_count=3):
    """获取数据库连接，带重试机制"""
    for i in range(retry_count):
        try:
            conn = pymysql.connect(**DB_CONFIG)
            logger.info("数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败 (尝试 {i+1}/{retry_count}): {e}")
            if i < retry_count - 1:
                time.sleep(2)
            else:
                raise


def reconnect_if_needed(conn):
    """检查连接是否有效，如果无效则重连"""
    try:
        conn.ping(reconnect=True)
        return conn
    except:
        logger.warning("连接已断开，尝试重新连接...")
        return get_connection()


def get_database_name(conn):
    """获取当前数据库名称"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        result = cursor.fetchone()
        db_name = list(result.values())[0] if result else None
        
        if not db_name:
            # 如果没有选中数据库，尝试查找包含all_stock表的数据库
            cursor.execute("SHOW DATABASES")
            databases = [list(row.values())[0] for row in cursor.fetchall()]
            
            for db in databases:
                if db in ['information_schema', 'mysql', 'performance_schema', 'sys']:
                    continue
                cursor.execute(f"USE `{db}`")
                cursor.execute("SHOW TABLES LIKE 'all_stock'")
                if cursor.fetchone():
                    logger.info(f"找到all_stock表所在的数据库: {db}")
                    return db
            
            raise Exception("未找到包含all_stock表的数据库")
        
        return db_name


def add_delisted_column(conn, db_name):
    """添加是否退市列（如果不存在）"""
    with conn.cursor() as cursor:
        try:
            # 检查列是否已存在
            cursor.execute(f"""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = '{db_name}' 
                AND TABLE_NAME = 'all_stock' 
                AND COLUMN_NAME = '是否退市'
            """)
            
            if cursor.fetchone():
                logger.info("'是否退市'列已存在")
            else:
                # 添加列
                cursor.execute("""
                    ALTER TABLE all_stock 
                    ADD COLUMN 是否退市 TINYINT(1) DEFAULT 0 COMMENT '0:未退市, 1:已退市'
                """)
                conn.commit()
                logger.info("成功添加'是否退市'列")
        except Exception as e:
            logger.error(f"添加列时出错: {e}")
            conn.rollback()
            raise


def get_all_stock_codes(conn):
    """获取所有股票代码"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT code FROM all_stock WHERE code IS NOT NULL")
        results = cursor.fetchall()
        stock_codes = [row['code'] for row in results]
        logger.info(f"共找到 {len(stock_codes)} 只股票")
        return stock_codes


def check_table_exists(conn, table_name):
    """检查表是否存在"""
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        return cursor.fetchone() is not None


def get_latest_date(conn, stock_code):
    """获取指定股票的最新K线数据日期"""
    # 表名使用小写
    table_name = f"basic_data_{stock_code.lower()}"
    
    # 检查表是否存在
    if not check_table_exists(conn, table_name):
        logger.warning(f"表 {table_name} 不存在")
        return None
    
    try:
        with conn.cursor() as cursor:
            # 查询最新的shi_jian（字段名是shi_jian，有下划线）
            cursor.execute(f"""
                SELECT MAX(shi_jian) as latest_date 
                FROM `{table_name}`
            """)
            result = cursor.fetchone()
            
            if result and result['latest_date']:
                return result['latest_date']
            else:
                logger.warning(f"表 {table_name} 中没有数据")
                return None
    except Exception as e:
        logger.error(f"查询表 {table_name} 时出错: {e}")
        return None


def update_delisted_status(conn, stock_code, is_delisted):
    """更新股票的退市状态"""
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE all_stock 
            SET 是否退市 = %s 
            WHERE code = %s
        """, (1 if is_delisted else 0, stock_code))


def main():
    """主函数"""
    conn = None
    try:
        # 连接数据库
        conn = get_connection()
        
        # 获取数据库名称
        db_name = get_database_name(conn)
        logger.info(f"使用数据库: {db_name}")
        
        # 确保使用正确的数据库
        with conn.cursor() as cursor:
            cursor.execute(f"USE `{db_name}`")
        
        # 添加是否退市列
        add_delisted_column(conn, db_name)
        
        # 获取所有股票代码
        stock_codes = get_all_stock_codes(conn)
        
        # 统计信息
        total = len(stock_codes)
        delisted_count = 0
        active_count = 0
        no_data_count = 0
        
        logger.info("开始检查股票退市状态...")
        
        # 遍历所有股票
        for idx, stock_code in enumerate(stock_codes, 1):
            try:
                # 每10次检查一次连接
                if idx % 10 == 1:
                    conn = reconnect_if_needed(conn)
                
                logger.info(f"处理进度: {idx}/{total} - 股票代码: {stock_code}")
                
                # 获取最新K线日期
                latest_date = get_latest_date(conn, stock_code)
                
                if latest_date is None:
                    # 没有数据的股票，标记为退市
                    update_delisted_status(conn, stock_code, True)
                    delisted_count += 1
                    no_data_count += 1
                    logger.info(f"  {stock_code}: 无数据 -> 标记为退市")
                else:
                    # 转换为datetime对象进行比较
                    if isinstance(latest_date, str):
                        latest_date = datetime.strptime(latest_date, '%Y-%m-%d')
                    
                    # 判断是否退市
                    is_delisted = latest_date < DELISTED_DATE
                    update_delisted_status(conn, stock_code, is_delisted)
                    
                    if is_delisted:
                        delisted_count += 1
                        logger.info(f"  {stock_code}: 最新日期 {latest_date.strftime('%Y-%m-%d')} -> 标记为退市")
                    else:
                        active_count += 1
                        logger.info(f"  {stock_code}: 最新日期 {latest_date.strftime('%Y-%m-%d')} -> 正常交易")
                
                # 每处理50只股票提交一次（减少间隔以降低数据丢失风险）
                if idx % 50 == 0:
                    conn.commit()
                    logger.info(f"已提交前 {idx} 只股票的更新")
                    
            except Exception as e:
                logger.error(f"处理股票 {stock_code} 时出错: {e}")
                # 尝试重连
                try:
                    conn = get_connection()
                    with conn.cursor() as cursor:
                        cursor.execute(f"USE stock")
                    logger.info("已重新连接数据库")
                except:
                    logger.error("重连失败，跳过当前股票")
                continue
        
        # 最终提交
        conn.commit()
        logger.info("=" * 60)
        logger.info("更新完成!")
        logger.info(f"总股票数: {total}")
        logger.info(f"已退市: {delisted_count} (其中无数据: {no_data_count})")
        logger.info(f"正常交易: {active_count}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"执行过程中出错: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
    finally:
        if conn:
            try:
                conn.close()
                logger.info("数据库连接已关闭")
            except:
                pass


if __name__ == "__main__":
    main()

