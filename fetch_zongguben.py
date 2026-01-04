#!/usr/bin/env python3
"""
从大智慧接口获取全部股票的流通A股数据，并更新到生产数据库的all_stock表中
"""

import logging
import time
from typing import List, Optional

import pymysql

from dzh_refresh.dzh_client import build_default_client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host='sh-cdb-2hxu41ka.sql.tencentcdb.com',
        port=21648,
        user='root',
        password='MrEPYZus7myr',
        database='stock',
        charset='utf8mb4'
    )


def get_all_stock_codes() -> List[str]:
    """从数据库获取所有股票代码"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM all_stock WHERE code IS NOT NULL")
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def fetch_liutongagu(client, stock_code: str) -> Optional[str]:
    """从大智慧接口获取单个股票的流通A股"""
    try:
        params = {
            "obj": stock_code,
            "field": "LiuTongAGu"
        }

        payload = client._request("/quote/stkdata", params)

        if payload.get("Err") != 0:
            logger.warning(f"获取{stock_code}流通A股失败: {payload}")
            return None

        data = payload.get("Data", {})
        rep_data = data.get("RepDataStkData", [])

        if not rep_data:
            logger.warning(f"{stock_code}没有返回数据")
            return None

        liutongagu = rep_data[0].get("LiuTongAGu")
        if liutongagu is not None:
            return str(liutongagu)
        else:
            logger.warning(f"{stock_code}的流通A股字段为空")
            return None

    except Exception as e:
        logger.error(f"获取{stock_code}流通A股时出错: {e}")
        return None


def update_liutongagu_batch(updates: List[tuple]):
    """批量更新流通A股数据"""
    if not updates:
        return

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 使用批量更新
        sql = "UPDATE all_stock SET LiuTongAGu = %s WHERE code = %s"
        cursor.executemany(sql, updates)

        conn.commit()
        logger.info(f"批量更新了 {len(updates)} 条记录")

    except Exception as e:
        logger.error(f"批量更新失败: {e}")
        conn.rollback()
    finally:
        conn.close()


def main(limit: int = None):
    """主函数"""
    logger.info("开始获取全部股票的流通A股数据...")

    # 获取所有股票代码
    stock_codes = get_all_stock_codes()
    if limit:
        stock_codes = stock_codes[:limit]
    logger.info(f"共处理 {len(stock_codes)} 只股票")

    # 初始化大智慧客户端
    client = build_default_client()

    # 批量处理参数
    batch_size = 50  # 每50个股票批量更新一次
    current_batch = []

    success_count = 0
    fail_count = 0

    for i, stock_code in enumerate(stock_codes, 1):
        logger.info(f"正在处理 {i}/{len(stock_codes)}: {stock_code}")

        # 获取流通A股
        liutongagu = fetch_liutongagu(client, stock_code)

        if liutongagu is not None:
            current_batch.append((liutongagu, stock_code))
            success_count += 1
            logger.info(f"{stock_code} 流通A股: {liutongagu}")
        else:
            fail_count += 1
            logger.warning(f"{stock_code} 获取流通A股失败")

        # 批量更新
        if len(current_batch) >= batch_size or i == len(stock_codes):
            update_liutongagu_batch(current_batch)
            current_batch = []

        # 添加延迟避免请求过快
        time.sleep(0.1)

    logger.info(f"处理完成! 成功: {success_count}, 失败: {fail_count}")


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
