#!/usr/bin/env python3
"""
计算换手率并更新到b_daily_chance表
换手率 = (当日成交量 / 流通A股数量) / 100
"""

import logging
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from datetime import date
import argparse

import pymysql

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


def get_stock_liutongagu(stock_code: str) -> Optional[float]:
    """获取股票的流通A股数量"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT LiuTongAGu FROM all_stock WHERE code=%s", (stock_code,))
        row = cursor.fetchone()
        if row and row[0]:
            return float(row[0])
        return None
    finally:
        conn.close()


def _basic_table_name(stock_code: str) -> str:
    return f"basic_data_{stock_code.lower()}"


def calculate_huanshou(volume: int, liutongagu: float) -> Optional[float]:
    """计算换手率"""
    if liutongagu and liutongagu > 0:
        # 换手率通常以百分比形式（例如 1.23 表示 1.23%），这里再除以 100
        return round(volume / liutongagu / 100, 4)
    return None


def load_all_stock_codes(
    limit: int = 0,
    offset: int = 0,
    codes: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    从 all_stock 获取股票代码列表（全量），支持 limit/offset 断点、或指定 codes。
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        params: List = []
        sql = "SELECT code FROM all_stock WHERE code IS NOT NULL"
        if codes:
            placeholders = ",".join(["%s"] * len(codes))
            sql += f" AND code IN ({placeholders})"
            params.extend([c.strip().upper() for c in codes if c.strip()])
        sql += " ORDER BY code"
        if limit and limit > 0:
            sql += " LIMIT %s"
            params.append(limit)
            if offset and offset > 0:
                sql += " OFFSET %s"
                params.append(offset)
        elif offset and offset > 0:
            # MySQL 允许超大 LIMIT 实现 OFFSET
            sql += " LIMIT 18446744073709551615 OFFSET %s"
            params.append(offset)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def load_b_daily_chance_dates_for_stock(
    stock_code: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    only_null: bool = True,
) -> List[date]:
    """
    从 b_daily_chance 中取该股票需要计算的日期列表。
    注意：我们只更新 b_daily_chance 里已存在的记录，避免插入缺少必填字段（stock_name 等）的行。
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        where = ["stock_code=%s"]
        params: List = [stock_code]
        if only_null:
            where.append("Huanshou IS NULL")
        if start:
            where.append("date >= %s")
            params.append(start)
        if end:
            where.append("date <= %s")
            params.append(end)
        sql = f"SELECT date FROM b_daily_chance WHERE {' AND '.join(where)} ORDER BY date"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def load_daily_volumes_for_stock(
    stock_code: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[date, int]:
    """
    从 basic_data_{code} 取日线成交量，返回 {date: volume}。
    """
    table = _basic_table_name(stock_code)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        where = ["peroid_type='1day'"]
        params: List = []
        if start:
            where.append("DATE(shi_jian) >= %s")
            params.append(start)
        if end:
            where.append("DATE(shi_jian) <= %s")
            params.append(end)
        sql = f"SELECT DATE(shi_jian) AS d, cheng_jiao_liang FROM {table} WHERE {' AND '.join(where)}"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        volumes: Dict[date, int] = {}
        for d, v in rows:
            if d is not None and v is not None:
                volumes[d] = int(v)
        return volumes
    finally:
        conn.close()


def update_huanshou_batch(updates: List[Tuple[str, str, date]]):
    """批量更新换手率（huanshou, stock_code, trade_date）"""
    if not updates:
        return

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 使用UPDATE语句，只更新已存在的记录
        sql = "UPDATE b_daily_chance SET Huanshou = %s WHERE stock_code = %s AND date = %s"
        cursor.executemany(sql, updates)

        conn.commit()
        logger.info(f"批量更新了 {len(updates)} 条记录")

    except Exception as e:
        logger.error(f"批量更新失败: {e}")
        conn.rollback()
    finally:
        conn.close()


def process_single_stock_test(stock_code: str = "SH600000", start: Optional[date] = None, end: Optional[date] = None):
    """测试单只股票的换手率计算（只打印，不写库）"""
    stock_code = stock_code.strip().upper()
    logger.info(f"测试股票: {stock_code}")

    liutongagu = get_stock_liutongagu(stock_code)
    if not liutongagu:
        logger.error(f"未找到 {stock_code} 的流通A股数据（all_stock.LiuTongAGu）")
        return
    logger.info(f"{stock_code} 流通A股: {liutongagu}")

    vols = load_daily_volumes_for_stock(stock_code, start=start, end=end)
    if not vols:
        logger.warning(f"{stock_code} 未获取到任何日线成交量数据（basic_data 表可能缺失或无数据）")
        return

    # 打印最近5个日期（按日期倒序）
    for d in sorted(vols.keys(), reverse=True)[:5]:
        v = vols[d]
        hs = calculate_huanshou(v, liutongagu)
        logger.info(f"{d}: 成交量={v}, 换手率={hs}")


def run(
    limit: int = 0,
    offset: int = 0,
    codes: Optional[Sequence[str]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    only_null: bool = True,
    batch_size: int = 500,
    sleep: float = 0.0,
    log_each_stock: bool = True,
) -> None:
    """
    全量按 all_stock 的股票集合跑：
    - 对每只股票，仅更新 b_daily_chance 里已存在的 (stock_code, date)
    - 成交量来自 basic_data_{code}.cheng_jiao_liang，period=1day
    """
    stock_codes = load_all_stock_codes(limit=limit, offset=offset, codes=codes)
    logger.info(f"all_stock 本次待处理股票数: {len(stock_codes)} (limit={limit}, offset={offset})")

    total_updates = 0
    total_missing_liutong = 0
    total_missing_volume = 0
    total_no_dates = 0
    current_batch: List[Tuple[str, str, date]] = []

    for idx, stock_code in enumerate(stock_codes, 1):
        stock_code = stock_code.strip().upper()
        if log_each_stock:
            logger.info(f"开始处理股票 {stock_code} ({idx}/{len(stock_codes)})")

        liutongagu = get_stock_liutongagu(stock_code)
        if not liutongagu:
            total_missing_liutong += 1
            logger.warning(f"{stock_code} 缺少 all_stock.LiuTongAGu，跳过")
            continue

        # b_daily_chance 里这个股票需要更新的日期
        dates = load_b_daily_chance_dates_for_stock(
            stock_code=stock_code, start=start, end=end, only_null=only_null
        )
        if not dates:
            total_no_dates += 1
            continue

        # basic_data 里拉一次成交量（范围可用 start/end 限制）
        try:
            vols = load_daily_volumes_for_stock(stock_code, start=start, end=end)
        except Exception as e:
            # 表不存在等情况
            logger.warning(f"{stock_code} 读取 {_basic_table_name(stock_code)} 失败: {e}")
            continue

        for d in dates:
            v = vols.get(d)
            if v is None:
                total_missing_volume += 1
                continue
            hs = calculate_huanshou(v, liutongagu)
            if hs is None:
                continue
            current_batch.append((str(hs), stock_code, d))
            total_updates += 1

            if len(current_batch) >= batch_size:
                update_huanshou_batch(current_batch)
                current_batch = []

        if sleep and sleep > 0:
            time.sleep(sleep)

    if current_batch:
        update_huanshou_batch(current_batch)

    logger.info(
        "完成: "
        f"更新={total_updates}, "
        f"缺少流通A股={total_missing_liutong}, "
        f"缺少成交量={total_missing_volume}, "
        f"无待更新日期={total_no_dates}"
    )


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(description="按 all_stock 全量计算 b_daily_chance.Huanshou（换手率）")
    parser.add_argument("--start", type=str, default="", help="开始日期 YYYY-MM-DD（可选）")
    parser.add_argument("--end", type=str, default="", help="结束日期 YYYY-MM-DD（可选）")
    parser.add_argument("--only-null", action="store_true", help="仅更新 Huanshou 为空的记录（默认开启）")
    parser.add_argument("--all", action="store_true", help="更新全部记录（忽略 Huanshou 是否为空）")
    parser.add_argument("--limit", type=int, default=0, help="限制处理股票数量（按 all_stock 顺序）")
    parser.add_argument("--offset", type=int, default=0, help="从第 offset 只股票开始（断点续跑）")
    parser.add_argument("--codes", type=str, default="", help="指定股票代码，逗号分隔，如 SH600000,SZ300188")
    parser.add_argument("--batch-size", type=int, default=500, help="每批更新条数")
    parser.add_argument("--sleep", type=float, default=0.0, help="每只股票处理完后的 sleep 秒数")
    parser.add_argument("--no-stock-log", action="store_true", help="关闭逐股票打印")
    parser.add_argument("--test", type=str, default="", help="仅测试单只股票（只打印不写库），如 SH600000")
    args = parser.parse_args()

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()] if args.codes else None
    only_null = True if args.only_null or not args.all else False

    if args.test:
        process_single_stock_test(args.test, start=start, end=end)
        return

    run(
        limit=args.limit,
        offset=args.offset,
        codes=codes,
        start=start,
        end=end,
        only_null=only_null,
        batch_size=args.batch_size,
        sleep=args.sleep,
        log_each_stock=not args.no_stock_log,
    )


if __name__ == "__main__":
    main()
