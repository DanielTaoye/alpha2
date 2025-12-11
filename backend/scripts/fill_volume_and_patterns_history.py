"""
从数据库批量回填历史成交量类型、多头组合、空头组合到 b_daily_chance。

特性：
- 默认只补齐 b_daily_chance 中 volume_type / bullish_pattern / bearish_pattern 为空的日期
- 支持 --force 强制重算全部日期
- 支持 --start / --end 限定日期区间
- 支持 --codes / --limit / --offset 控制股票范围

使用示例：
1) 全量补齐缺失：
   python fill_volume_and_patterns_history.py

2) 仅处理指定股票代码：
   python fill_volume_and_patterns_history.py --codes SZ301565,SH688701

3) 限定日期区间并强制重算：
   python fill_volume_and_patterns_history.py --start 2024-01-01 --end 2024-12-31 --force
"""

import sys
import os
import argparse
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple

import pymysql
import pymysql.cursors

# ===== 路径处理 =====
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

from domain.services.volume_type_service import VolumeTypeService
from domain.services.bullish_pattern_service import BullishPatternService
from domain.services.bearish_pattern_service import BearishPatternService

# ===== 数据库配置（生产主库） =====
MASTER_DB_CONFIG = {
    "host": "sh-cdb-2hxu41ka.sql.tencentcdb.com",
    "port": 21648,
    "user": "root",
    "password": "MrEPYZus7myr",
    "database": "stock",
    "charset": "utf8mb4",
}

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fill_volume_and_patterns_history")


# ========= 基础工具 =========
def get_master_connection():
    return pymysql.connect(**MASTER_DB_CONFIG)


def load_stocks_from_db(
    conn, limit: Optional[int], codes: Optional[List[str]], offset: int = 0
) -> List[Dict]:
    """
    从 all_stock 读取股票与 nature
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    where_clauses = ["(`是否退市` != 1 OR `是否退市` IS NULL)"]
    params: List = []
    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        where_clauses.append(f"code IN ({placeholders})")
        params.extend(codes)

    sql = f"""
        SELECT code, name, nature
        FROM all_stock
        WHERE {' AND '.join(where_clauses)}
        ORDER BY code
    """

    if limit and limit > 0:
        sql += " LIMIT %s"
        params.append(limit)
        if offset > 0:
            sql += " OFFSET %s"
            params.append(offset)
    elif offset > 0:
        sql += " LIMIT 18446744073709551615 OFFSET %s"
        params.append(offset)

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    stocks: List[Dict] = []
    for row in rows:
        stocks.append(
            {
                "code": (row.get("code") or "").upper(),
                "name": row.get("name") or "",
                "nature": row.get("nature") or "",
                "table_name": f"basic_data_{(row.get('code') or '').lower()}",
            }
        )

    logger.info(f"📊 加载股票数: {len(stocks)}")
    return stocks


def load_dates_for_stock(
    conn,
    stock_code: str,
    start_date: Optional[date],
    end_date: Optional[date],
    force: bool,
) -> List[date]:
    """
    读取 b_daily_chance 中该股票需要处理的日期
    - 默认仅挑选 volume/pattern 为空的数据
    - force=True 时忽略是否为空，直接取区间内全部日期
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    where = ["stock_code = %s"]
    params: List = [stock_code]

    if not force:
        where.append(
            "(volume_type IS NULL OR volume_type = '' "
            "OR bullish_pattern IS NULL OR bearish_pattern IS NULL "
            "OR bullish_pattern = '' OR bearish_pattern = '')"
        )

    if start_date:
        where.append("DATE(date) >= %s")
        params.append(start_date)
    if end_date:
        where.append("DATE(date) <= %s")
        params.append(end_date)

    sql = f"""
        SELECT DISTINCT DATE(date) AS d
        FROM b_daily_chance
        WHERE {' AND '.join(where)}
        ORDER BY d ASC
    """
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    dates: List[date] = []
    for r in rows:
        d = r.get("d")
        if isinstance(d, datetime):
            dates.append(d.date())
        elif isinstance(d, date):
            dates.append(d)
        elif d:
            try:
                dates.append(datetime.strptime(str(d), "%Y-%m-%d").date())
            except Exception:
                continue
    return dates


def fetch_daily_data(
    conn, table_name: str, start_date: date, end_date: date
) -> List[Dict]:
    """
    读取指定日期范围的日线数据，附带 prev_close，供多空组合识别。
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    query = f"""
        SELECT shi_jian AS date, kai_pan_jia AS open, shou_pan_jia AS close,
               zui_gao_jia AS high, zui_di_jia AS low, cheng_jiao_liang AS volume
        FROM {table_name}
        WHERE peroid_type = '1day'
          AND DATE(shi_jian) >= %s
          AND DATE(shi_jian) <= %s
        ORDER BY shi_jian ASC
    """
    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()

    daily: List[Dict] = []
    for idx, r in enumerate(rows):
        dt_val = r.get("date")
        if isinstance(dt_val, datetime):
            dt_obj = dt_val
        else:
            try:
                if isinstance(dt_val, str):
                    dt_obj = datetime.strptime(dt_val.split()[0], "%Y-%m-%d")
                else:
                    dt_obj = datetime.combine(dt_val, datetime.min.time())
            except Exception:
                dt_obj = None

        item = {
            "date": dt_obj,
            "open": float(r.get("open") or 0),
            "close": float(r.get("close") or 0),
            "high": float(r.get("high") or 0),
            "low": float(r.get("low") or 0),
            "volume": (int(r.get("volume") or 0) / 100),
        }
        if idx > 0:
            prev_close_raw = rows[idx - 1].get("close")
            item["prev_close"] = float(prev_close_raw) if prev_close_raw else 0
        daily.append(item)
    return daily


# ========= 组合计算（基于已缓存的日线数据，避免重复查库） =========
def _get_index_map(daily_data: List[Dict]) -> Dict[date, int]:
    idx_map: Dict[date, int] = {}
    for i, item in enumerate(daily_data):
        dt_val = item.get("date")
        if isinstance(dt_val, datetime):
            idx_map[dt_val.date()] = i
        elif isinstance(dt_val, date):
            idx_map[dt_val] = i
    return idx_map


def _check_abc_volume_type_local(daily_data: List[Dict], idx: int) -> Optional[str]:
    """本地计算 A/B/C（不查库）"""
    if idx < 1:
        return None
    target_volume = daily_data[idx]["volume"]
    # A
    prev_volume = daily_data[idx - 1]["volume"]
    if prev_volume > 0:
        ratio = target_volume / prev_volume
        if 2.0 <= ratio <= 3.0:
            return "A"
    # B
    if idx >= 3:
        prev_3 = [daily_data[i]["volume"] for i in range(idx - 3, idx)]
        avg3 = sum(prev_3) / len(prev_3)
        if avg3 > 0 and target_volume / avg3 >= 2.0:
            return "B"
    # C
    if idx >= 5:
        prev_5 = [daily_data[i]["volume"] for i in range(idx - 5, idx)]
        avg5 = sum(prev_5) / len(prev_5)
        if avg5 > 0 and target_volume / avg5 >= 2.0:
            return "C"
    return None


def calculate_volume_type_cached(daily_data: List[Dict], target_idx: int) -> Optional[str]:
    """
    纯使用缓存的日线数据计算成交量类型（减少 DB 调用）
    """
    if target_idx < 1 or target_idx >= len(daily_data):
        return None

    target_volume = daily_data[target_idx]["volume"]
    matched: List[str] = []

    # A
    prev_volume = daily_data[target_idx - 1]["volume"]
    if prev_volume > 0:
        ratio = target_volume / prev_volume
        if 2.0 <= ratio <= 3.0:
            matched.append("A")

    # B
    if target_idx >= 3:
        prev_3 = [daily_data[i]["volume"] for i in range(target_idx - 3, target_idx)]
        avg3 = sum(prev_3) / len(prev_3)
        if avg3 > 0 and target_volume / avg3 >= 2.0:
            matched.append("B")

    # C
    if target_idx >= 5:
        prev_5 = [daily_data[i]["volume"] for i in range(target_idx - 5, target_idx)]
        avg5 = sum(prev_5) / len(prev_5)
        if avg5 > 0 and target_volume / avg5 >= 2.0:
            matched.append("C")

    # D
    if target_idx >= 5:
        x_day_volume = None
        for i in range(max(0, target_idx - 5), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                x_day_volume = daily_data[i]["volume"]
                break
        if x_day_volume and x_day_volume > 0:
            ratio = target_volume / x_day_volume
            if ratio >= 1.2:
                matched.append("D")

    # E
    if target_idx >= 5:
        has_abcd = False
        for i in range(max(0, target_idx - 5), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                has_abcd = True
                break
        if not has_abcd:
            prev_volume = daily_data[target_idx - 1]["volume"]
            prev_5 = [daily_data[i]["volume"] for i in range(target_idx - 5, target_idx)]
            avg5 = sum(prev_5) / len(prev_5)
            if prev_volume > 0 and avg5 > 0:
                if target_volume / prev_volume >= 4.0 and target_volume / avg5 >= 4.0:
                    matched.append("E")

    # F
    if target_idx >= 5:
        x_day_volume = None
        for i in range(max(0, target_idx - 5), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                x_day_volume = daily_data[i]["volume"]
                break
        prev_5 = [daily_data[i]["volume"] for i in range(target_idx - 5, target_idx)]
        avg5 = sum(prev_5) / len(prev_5)
        cond1 = x_day_volume and x_day_volume > 0 and target_volume / x_day_volume >= 3.0
        cond2 = avg5 > 0 and target_volume / avg5 >= 3.0
        if cond1 or cond2:
            matched.append("F")

    # G
    if target_idx >= 5:
        for i in range(max(0, target_idx - 5), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                x_day_volume = daily_data[i]["volume"]
                if x_day_volume > 0 and target_volume / x_day_volume >= 0.7:
                    matched.append("G")
                    break

    # H
    if target_idx >= 5:
        for i in range(max(0, target_idx - 5), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                x_day_volume = daily_data[i]["volume"]
                if target_volume > x_day_volume:
                    matched.append("H")
                    break

    # X
    if target_idx >= 3:
        prev_3 = [daily_data[i]["volume"] for i in range(target_idx - 3, target_idx)]
        avg3 = sum(prev_3) / len(prev_3)
        if avg3 > 0 and target_volume / avg3 >= 1.5:
            matched.append("X")

    # Y
    if target_idx >= 5:
        prev_5 = [daily_data[i]["volume"] for i in range(target_idx - 5, target_idx)]
        avg5 = sum(prev_5) / len(prev_5)
        if avg5 > 0 and target_volume / avg5 >= 1.5:
            matched.append("Y")

    # Z
    if target_idx >= 10:
        has_abc_in_prev_10 = False
        for i in range(max(0, target_idx - 10), target_idx):
            abc = _check_abc_volume_type_local(daily_data, i)
            if abc in ["A", "B", "C"]:
                has_abc_in_prev_10 = True
                break
        if has_abc_in_prev_10 and target_idx >= 4:
            yesterday_volume = daily_data[target_idx - 1]["volume"]
            prev_3 = [daily_data[i]["volume"] for i in range(target_idx - 4, target_idx - 1)]
            avg3 = sum(prev_3) / len(prev_3) if prev_3 else 0
            cond1 = avg3 > 0 and yesterday_volume / avg3 >= 1.3
            cond2 = yesterday_volume > 0 and target_volume / yesterday_volume >= 1.08
            if cond1 and cond2:
                matched.append("Z")

    if not matched:
        return None

    # 去重并按既定顺序
    order = ["A", "B", "C", "D", "E", "F", "G", "H", "X", "Y", "Z"]
    seen = set()
    ordered = []
    for t in order:
        if t in matched and t not in seen:
            ordered.append(t)
            seen.add(t)
    return ",".join(ordered) if ordered else None


def evaluate_bullish_patterns(
    stock_code: str, table_name: str, daily_data: List[Dict], target_idx: int
) -> List[str]:
    if target_idx < 0 or target_idx >= len(daily_data):
        return []
    today = daily_data[target_idx]
    prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None

    matched: List[str] = []
    p1 = BullishPatternService._check_pattern1(stock_code, prev_day, today)
    if p1:
        matched.append(p1)
    p2 = BullishPatternService._check_pattern2(stock_code, prev_day, today)
    if p2:
        matched.append(p2)
    p3 = BullishPatternService._check_pattern3(stock_code, prev_day, today)
    if p3:
        matched.append(p3)
    p4 = BullishPatternService._check_pattern4(stock_code, prev_day, today)
    if p4:
        matched.append(p4)
    p5 = BullishPatternService._check_pattern5(stock_code, prev_day, today)
    if p5:
        matched.append(p5)
    p6 = BullishPatternService._check_pattern6(stock_code, daily_data, target_idx)
    if p6:
        matched.append(p6)
    p7 = BullishPatternService._check_pattern7(
        stock_code, table_name, daily_data, target_idx
    )
    if p7:
        matched.append(p7)
    return matched


def evaluate_bearish_patterns(
    stock_code: str, table_name: str, daily_data: List[Dict], target_idx: int
) -> List[str]:
    if target_idx < 0 or target_idx >= len(daily_data):
        return []
    today = daily_data[target_idx]
    prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None

    matched: List[str] = []

    checks = [
        BearishPatternService._check_pattern1,
        BearishPatternService._check_pattern2,
        BearishPatternService._check_pattern3,
        BearishPatternService._check_pattern4,
        BearishPatternService._check_pattern5,
        BearishPatternService._check_pattern6,
        BearishPatternService._check_pattern7,
        BearishPatternService._check_pattern8,
        BearishPatternService._check_pattern9,
        BearishPatternService._check_pattern10,
        BearishPatternService._check_pattern11,
        BearishPatternService._check_pattern12,
        BearishPatternService._check_pattern13,
        BearishPatternService._check_pattern14,
    ]

    for func in checks:
        try:
            if func.__name__ in {"_check_pattern4", "_check_pattern5", "_check_pattern9", "_check_pattern12", "_check_pattern13", "_check_pattern14"}:
                res = func(stock_code, daily_data, target_idx)
            elif func.__name__ in {"_check_pattern6", "_check_pattern7", "_check_pattern8", "_check_pattern10", "_check_pattern11"}:
                res = func(stock_code, prev_day, today)
            else:
                res = func(stock_code, prev_day, today)
        except Exception:
            res = None
        if res:
            matched.append(res)

    return matched


# ========= 数据库写入 =========
def batch_update_volume_and_patterns(conn, updates: List[Tuple[str, str, str, str, str]]) -> int:
    """
    updates: [(volume_type, bullish_pattern, bearish_pattern, stock_code, date_str)]
    """
    if not updates:
        return 0
    cursor = conn.cursor()
    sql = """
        UPDATE b_daily_chance
        SET volume_type = %s,
            bullish_pattern = %s,
            bearish_pattern = %s,
            updated_at = NOW()
        WHERE stock_code = %s AND DATE(date) = %s
    """
    cursor.executemany(sql, updates)
    conn.commit()
    return len(updates)


# ========= 核心处理 =========
def process_stock(
    master_conn,
    data_conn,
    stock: Dict,
    start_dt: Optional[date],
    end_dt: Optional[date],
    force: bool,
) -> int:
    """
    处理单只股票：
    - 找出需要填充的日期
    - 计算成交量类型、多头/空头组合
    - 批量更新
    """
    code = stock["code"]
    name = stock["name"]
    table_name = stock.get("table_name") or f"basic_data_{code.lower()}"

    try:
        dates = load_dates_for_stock(master_conn, code, start_dt, end_dt, force)
        if not dates:
            logger.info(f"  ℹ️ {code} 无需处理（无目标日期）")
            return 0

        min_date = min(dates)
        max_date = max(dates)
        logger.info(
            f"  🗓️ {code} 需处理日期 {len(dates)} 个，范围 {min_date} ~ {max_date}"
        )

        # 1) 成交量类型批量计算（减少数据库往返）
        volume_types = VolumeTypeService.batch_calculate_volume_types(
            table_name,
            stock_code=code,
            start_date=datetime.combine(min_date, datetime.min.time()),
            end_date=datetime.combine(max_date, datetime.min.time()),
        )
        volume_map = (
            {dt.date(): vt for dt, vt in volume_types.items()} if volume_types else {}
        )
        logger.info(
            f"  📈 {code} 批量成交量类型获取 {len(volume_map)} 条（缺失将单日补算）"
        )

        # 2) 读取日线数据（多空组合使用）
        buffer_start = min_date - timedelta(days=25)
        daily_data = fetch_daily_data(data_conn, table_name, buffer_start, max_date)
        if not daily_data:
            logger.info(f"  ⚠️ {code} 无日线数据，跳过")
            return 0
        idx_map = _get_index_map(daily_data)
        logger.info(f"  🪙 {code} 日线缓存 {len(daily_data)} 条")

        updates: List[Tuple[str, str, str, str, str]] = []
        for d in dates:
            target_idx = idx_map.get(d)
            if target_idx is None:
                continue

            volume_type = volume_map.get(d)
            if not volume_type:
                # 回退到本地缓存计算，避免频繁查库
                volume_type = calculate_volume_type_cached(daily_data, target_idx)

            bullish_list = evaluate_bullish_patterns(
                code, table_name, daily_data, target_idx
            )
            bearish_list = evaluate_bearish_patterns(
                code, table_name, daily_data, target_idx
            )

            bullish_str = ",".join(bullish_list) if bullish_list else ""
            bearish_str = ",".join(bearish_list) if bearish_list else ""

            updates.append(
                (
                    volume_type or "",
                    bullish_str,
                    bearish_str,
                    code,
                    d.strftime("%Y-%m-%d"),
                )
            )

        if not updates:
            logger.info(f"  ℹ️ {code} 无可更新记录")
            return 0

        updated = batch_update_volume_and_patterns(master_conn, updates)
        logger.info(f"  ✅ {code} {name} 更新 {updated} 条")
        return updated
    except Exception as e:
        logger.error(f"  ❌ {code} 处理失败: {e}", exc_info=True)
        return 0


def run_once(
    start_dt: Optional[date],
    end_dt: Optional[date],
    limit: int,
    offset: int,
    codes: Optional[List[str]],
    force: bool,
):
    try:
        master_conn = get_master_connection()
        data_conn = get_master_connection()
        logger.info(f"✅ 已连接主库 {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
    except Exception as e:
        logger.error(f"❌ 连接主库失败: {e}")
        return

    stocks = load_stocks_from_db(master_conn, limit=limit, codes=codes, offset=offset)
    if not stocks:
        logger.error("❌ 未加载到任何股票")
        master_conn.close()
        data_conn.close()
        return

    total_rows = 0
    try:
        for i, stock in enumerate(stocks, 1):
            logger.info(f"[{i}/{len(stocks)}] 处理 {stock['code']} ({stock['name']}) ...")
            total_rows += process_stock(master_conn, data_conn, stock, start_dt, end_dt, force)
    finally:
        master_conn.close()
        data_conn.close()
        logger.info("✅ 已关闭数据库连接")

    logger.info("📊 完成")
    logger.info(f"总写入/更新: {total_rows} 条")


def parse_args():
    parser = argparse.ArgumentParser(
        description="批量回填历史成交量类型、多头/空头组合到 b_daily_chance"
    )
    parser.add_argument("--start", type=str, help="开始日期 YYYY-MM-DD，可选")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD，可选")
    parser.add_argument("--limit", type=int, default=0, help="限制股票数量（测试用）")
    parser.add_argument("--offset", type=int, default=0, help="从第 offset 条开始")
    parser.add_argument("--codes", type=str, help="指定股票代码，逗号分隔，如 SZ301565,SH688701")
    parser.add_argument("--force", action="store_true", help="强制重算所有日期（忽略是否已有值）")
    return parser.parse_args()


def main():
    args = parse_args()

    start_dt = None
    end_dt = None
    if args.start:
        try:
            start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
        except Exception:
            logger.error("❌ start 日期格式错误，应为 YYYY-MM-DD")
            sys.exit(1)
    if args.end:
        try:
            end_dt = datetime.strptime(args.end, "%Y-%m-%d").date()
        except Exception:
            logger.error("❌ end 日期格式错误，应为 YYYY-MM-DD")
            sys.exit(1)

    codes = None
    if args.codes:
        codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()]

    run_once(
        start_dt=start_dt,
        end_dt=end_dt,
        limit=args.limit,
        offset=args.offset,
        codes=codes,
        force=args.force,
    )


if __name__ == "__main__":
    main()

