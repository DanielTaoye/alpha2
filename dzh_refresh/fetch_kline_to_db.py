import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pymysql

# 兼容两种启动方式：
# 1) python .\dzh_refresh\fetch_kline_to_db.py   （sys.path 默认是 dzh_refresh 目录，会导致 `import dzh_refresh` 失败）
# 2) python -m dzh_refresh.fetch_kline_to_db    （推荐）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dzh_refresh.dzh_client import DzhRestClient, build_default_client
from dzh_refresh.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")

def _parse_int(s: Optional[str], default: int) -> int:
    try:
        if s is None:
            return default
        return int(s)
    except Exception:
        return default


def _env_or_default() -> Dict[str, any]:
    obj = os.getenv("DZH_OBJ", "SH601128")
    start = os.getenv("DZH_START", "2024-01-01")
    end = os.getenv("DZH_END", "2025-01-01")
    return {
        "obj": obj,
        "table": os.getenv("DZH_TABLE", f"basic_data_{obj.lower()}"),
        "period": os.getenv("DZH_PERIOD", "1day"),
        "start": _parse_date(start),
        "end": _parse_date(end),
        "count": _parse_int(os.getenv("DZH_COUNT"), 600),
        "stock_list": os.getenv("DZH_STOCK_LIST", "stock_list.csv"),
    }


def _ensure_table_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    """Create K线表（如果不存在），对齐历史表结构，去掉 zuo_shou_jia / cheng_jiao_bi_shu。"""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
      `peroid_type` varchar(20) DEFAULT NULL COMMENT '周期类型',
      `shi_jian` datetime NOT NULL COMMENT '时间',
      `kai_pan_jia` decimal(30,2) DEFAULT NULL COMMENT '开盘价',
      `zui_gao_jia` decimal(30,2) DEFAULT NULL COMMENT '最高价',
      `zui_di_jia` decimal(30,2) DEFAULT NULL COMMENT '最低价',
      `shou_pan_jia` decimal(30,2) DEFAULT NULL COMMENT '收盘价',
      `cheng_jiao_liang` bigint DEFAULT NULL COMMENT '成交量',
      `cheng_jiao_e` decimal(30,2) DEFAULT NULL COMMENT '成交额',
      `shi_zhi` decimal(30,2) DEFAULT NULL COMMENT '市值',
      `liu_tong_shi_zhi` decimal(30,2) DEFAULT NULL COMMENT '流通市值',
      `baidu_score` decimal(5,2) DEFAULT NULL COMMENT '百度股市通评分',
      `tonghuashun_score` decimal(5,2) DEFAULT NULL COMMENT '同花顺评分',
      `dongfang_score` decimal(5,2) DEFAULT NULL COMMENT '东方财富网评分',
      `shi_ying_lv_dong` decimal(30,2) DEFAULT NULL COMMENT '市盈率（动）',
      `shi_ying_lv_jing` decimal(30,2) DEFAULT NULL COMMENT '市盈率（静）',
      `shi_ying_lv_ttm` decimal(30,2) DEFAULT NULL COMMENT '市盈率TTM',
      `shi_jing_lv` decimal(30,2) DEFAULT NULL COMMENT '市净率',
      `mei_gu_shou_yi` decimal(30,2) DEFAULT NULL COMMENT '每股收益',
      `mei_gu_jing_zi_chan` decimal(30,2) DEFAULT NULL COMMENT '每股净资产',
      `zong_gu_ben` bigint DEFAULT NULL COMMENT '总股本',
      `liu_tong_gu_ben` bigint DEFAULT NULL COMMENT '流通股本',
      `shang_yu_bi` decimal(5,2) DEFAULT NULL COMMENT '商誉/净资产占比',
      `gu_xi` decimal(30,2) DEFAULT NULL COMMENT '股息',
      `huan_shou_lv` decimal(5,2) DEFAULT NULL COMMENT '换手率',
      `zhen_fu` decimal(5,2) DEFAULT NULL COMMENT '振幅',
      `industry_id_1` int DEFAULT NULL COMMENT '1级行业分类',
      `industry_id_2` int DEFAULT NULL COMMENT '2级行业分类',
      `industry_id_3` int DEFAULT NULL COMMENT '3级行业分类',
      `dom_festival_type` int DEFAULT NULL COMMENT '国内节日类型',
      `dom_festival_relation_type` int DEFAULT NULL COMMENT '国内节日相对类型',
      `int_festival_type` int DEFAULT NULL COMMENT '国际节日类型',
      `int_festival_relation_type` int DEFAULT NULL COMMENT '国际节日相对类型',
      `year` int DEFAULT NULL,
      `month` int DEFAULT NULL,
      `day_in_month` int DEFAULT NULL,
      `hour_in_day` int DEFAULT NULL,
      `sh_index` decimal(30,2) DEFAULT NULL COMMENT '上证指数',
      `sz_index` decimal(30,2) DEFAULT NULL COMMENT '深证指数',
      `cy_index` decimal(30,2) DEFAULT NULL COMMENT '创业板指数',
      `zx_100_index` decimal(30,2) DEFAULT NULL COMMENT '中小100',
      `hs_300_index` decimal(30,2) DEFAULT NULL COMMENT '沪深300',
      `sh_50_index` decimal(30,2) DEFAULT NULL COMMENT '上证50',
      `sh_380_index` decimal(30,2) DEFAULT NULL COMMENT '上证380',
      `hs_index` decimal(30,2) DEFAULT NULL COMMENT '恒生指数',
      `gq_index` decimal(30,2) DEFAULT NULL COMMENT '国企指数',
      `hc_index` decimal(30,2) DEFAULT NULL COMMENT '红筹指数',
      `nsdk_index` decimal(30,2) DEFAULT NULL COMMENT '纳斯达克指数',
      `dqs_index` decimal(30,2) DEFAULT NULL COMMENT '道琼斯指数',
      `bp_500_index` decimal(30,2) DEFAULT NULL COMMENT '标普500指数',
      `create_time` datetime DEFAULT NULL COMMENT '创建时间',
      `update_time` datetime DEFAULT NULL COMMENT '更新时间',
      `creator` varchar(255) DEFAULT NULL COMMENT '创建者',
      `last_operator` varchar(255) DEFAULT NULL COMMENT '更新者',
      PRIMARY KEY (`id`),
      UNIQUE KEY `shi_jian_index` (`shi_jian`,`peroid_type`) USING BTREE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cursor:
        cursor.execute(ddl)
    conn.commit()


def _ensure_columns(conn: pymysql.connections.Connection, table_name: str) -> None:
    """确保关键列存在，缺失则自动补充（当前无需新增额外列）。"""
    needed = {}
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`;")
        existing: Set[str] = {row[0] for row in cursor.fetchall()}
        for col, definition in needed.items():
            if col not in existing:
                cursor.execute(
                    f"ALTER TABLE `{table_name}` ADD COLUMN {col} {definition};"
                )
                logger.info("为表 %s 补充列 %s", table_name, col)
    conn.commit()

def _dt_range_end_exclusive(end_dt_inclusive: datetime) -> datetime:
    """把包含式 end_dt 转成 [start, end_exclusive) 右开区间，避免 datetime 时分秒差异导致漏删/漏查。"""
    return datetime(end_dt_inclusive.year, end_dt_inclusive.month, end_dt_inclusive.day) + timedelta(days=1)


def _normalize_1day_value(v):
    # 统一比较口径：价格/成交额保留原值（通常是 Decimal/float/str），成交量转 int
    return v


def _bar_to_1day_key_value(bar: Dict) -> Optional[Tuple[datetime.date, Tuple]]:
    ts = bar.get("ShiJian")
    if ts is None:
        return None

    dt = datetime.fromtimestamp(int(ts))
    d = dt.date()
    value = (
        _normalize_1day_value(bar.get("KaiPanJia")),
        _normalize_1day_value(bar.get("ZuiGaoJia")),
        _normalize_1day_value(bar.get("ZuiDiJia")),
        _normalize_1day_value(bar.get("ShouPanJia")),
        int(bar.get("ChengJiaoLiang") or 0),
        _normalize_1day_value(bar.get("ChengJiaoE")),
    )
    return d, value


def _day_to_midnight(d) -> datetime:
    return datetime(d.year, d.month, d.day)


def _load_existing_1day_map(
    conn: pymysql.connections.Connection,
    table_name: str,
    period_type: str,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[datetime.date, Tuple]:
    """
    读取 DB 中指定日期范围内的 1day 数据，按 date 维度做对比。
    - 查询使用 [start, end_exclusive) 避免 shi_jian 时分秒不同导致漏查。
    """
    start_floor = datetime(start_dt.year, start_dt.month, start_dt.day)
    end_exclusive = _dt_range_end_exclusive(end_dt)
    sql = f"""
    SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang, cheng_jiao_e
    FROM `{table_name}`
    WHERE peroid_type = %s
      AND shi_jian >= %s
      AND shi_jian < %s
    ORDER BY shi_jian ASC
    """
    out: Dict[datetime.date, Tuple] = {}
    with conn.cursor() as cursor:
        cursor.execute(sql, (period_type, start_floor, end_exclusive))
        rows = cursor.fetchall() or []
        for row in rows:
            shi_jian = row[0]
            if not shi_jian:
                continue
            d = shi_jian.date()
            # 如果同一天出现多条，直接视为不一致（用特殊占位触发更新）
            if d in out:
                out[d] = ("__DUP__",)
                continue
            out[d] = (
                _normalize_1day_value(row[1]),
                _normalize_1day_value(row[2]),
                _normalize_1day_value(row[3]),
                _normalize_1day_value(row[4]),
                int(row[5] or 0),
                _normalize_1day_value(row[6]),
            )
    return out


def _delete_existing_1day_range(
    conn: pymysql.connections.Connection,
    table_name: str,
    period_type: str,
    start_dt: datetime,
    end_dt: datetime,
) -> int:
    start_floor = datetime(start_dt.year, start_dt.month, start_dt.day)
    end_exclusive = _dt_range_end_exclusive(end_dt)
    sql = f"""
    DELETE FROM `{table_name}`
    WHERE peroid_type = %s
      AND shi_jian >= %s
      AND shi_jian < %s
    """
    with conn.cursor() as cursor:
        affected = cursor.execute(sql, (period_type, start_floor, end_exclusive))
    return int(affected or 0)


def _save_bars_replace_range_1day(
    conn: pymysql.connections.Connection,
    table_name: str,
    period_type: str,
    bars: List[Dict],
    start_dt: datetime,
    end_dt: datetime,
) -> int:
    """
    覆盖更新指定范围内的 1day：
    - 先删 [start, end_exclusive) 范围内该 period 的旧数据
    - 再批量写入（insert）
    """
    if not bars:
        # 没有新数据，仍然不做删除，避免误清空
        return 0

    _ensure_table_exists(conn, table_name)
    _ensure_columns(conn, table_name)

    start_date = start_dt.date()
    end_date = end_dt.date()

    payloads: List[tuple] = []
    for bar in bars:
        kv = _bar_to_1day_key_value(bar)
        if kv is None:
            continue
        d, value = kv
        if d < start_date or d > end_date:
            continue

        # 约定：1day 的 shi_jian 一律写当日 00:00:00
        dt = _day_to_midnight(d)
        payloads.append(
            (
                period_type,
                dt,
                value[0],
                value[1],
                value[2],
                value[3],
                value[4],
                value[5],
            )
        )

    if not payloads:
        return 0

    insert_sql = f"""
    INSERT INTO `{table_name}` (
        peroid_type, shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
        cheng_jiao_liang, cheng_jiao_e
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s
    )
    """

    # 事务：删除 + 插入
    with conn.cursor() as cursor:
        deleted = _delete_existing_1day_range(conn, table_name, period_type, start_dt, end_dt)
        cursor.executemany(insert_sql, payloads)
    conn.commit()
    logger.info("表 %s 覆盖更新完成：删除 %s，写入 %s", table_name, deleted, len(payloads))
    return len(payloads)


def _save_bars(
    conn: pymysql.connections.Connection,
    table_name: str,
    period_type: str,
    bars: List[Dict],
) -> int:
    """Upsert bars into MySQL."""
    if not bars:
        return 0

    _ensure_table_exists(conn, table_name)
    _ensure_columns(conn, table_name)
    insert_sql = f"""
    INSERT INTO `{table_name}` (
        peroid_type, shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
        cheng_jiao_liang, cheng_jiao_e
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s
    ) ON DUPLICATE KEY UPDATE
        kai_pan_jia = VALUES(kai_pan_jia),
        zui_gao_jia = VALUES(zui_gao_jia),
        zui_di_jia = VALUES(zui_di_jia),
        shou_pan_jia = VALUES(shou_pan_jia),
        cheng_jiao_liang = VALUES(cheng_jiao_liang),
        cheng_jiao_e = VALUES(cheng_jiao_e);
    """

    payloads: List[tuple] = []
    for bar in bars:
        ts = bar.get("ShiJian")
        if ts is None:
            continue

        dt = datetime.fromtimestamp(int(ts))
        # 约定：1day 的 shi_jian 一律写当日 00:00:00
        if str(period_type).lower() == "1day":
            dt = _day_to_midnight(dt.date())
        payloads.append(
            (
                period_type,
                dt,
                bar.get("KaiPanJia"),
                bar.get("ZuiGaoJia"),
                bar.get("ZuiDiJia"),
                bar.get("ShouPanJia"),
                int(bar.get("ChengJiaoLiang") or 0),
                bar.get("ChengJiaoE"),
            )
        )

    if not payloads:
        return 0

    with conn.cursor() as cursor:
        cursor.executemany(insert_sql, payloads)
    conn.commit()
    return len(payloads)

def _read_text_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _decode_text(data: bytes) -> str:
    # stock_list.csv 里中文可能不是 utf-8，这里优先保证 code 列能读出来
    for enc in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


@dataclass(frozen=True)
class StockItem:
    code: str
    name: str = ""


def _load_stock_list(stock_list_path: str) -> List[StockItem]:
    if not os.path.exists(stock_list_path):
        raise FileNotFoundError(f"stock_list.csv 不存在: {stock_list_path}")

    import csv

    text = _decode_text(_read_text_bytes(stock_list_path))
    # csv 模块需要 file-like
    from io import StringIO

    f = StringIO(text)
    reader = csv.DictReader(f)
    out: List[StockItem] = []
    for row in reader:
        if not row:
            continue
        code = (row.get("code") or "").strip()
        if not code:
            continue
        name = (row.get("name") or "").strip()
        out.append(StockItem(code=code, name=name))
    return out


def _fetch_1day_map_from_api(
    client: DzhRestClient,
    obj: str,
    start_dt: datetime,
    end_dt: datetime,
    count: int,
) -> Dict[datetime.date, Tuple]:
    bars = client.fetch_kline(
        obj=obj,
        period="1day",
        begin_time=start_dt,
        end_time=end_dt,
        count=count,
        split=1,
    )
    start_date = start_dt.date()
    end_date = end_dt.date()
    out: Dict[datetime.date, Tuple] = {}
    for bar in bars:
        kv = _bar_to_1day_key_value(bar)
        if kv is None:
            continue
        d, value = kv
        if d < start_date or d > end_date:
            continue
        # 同一天多条也视为异常（触发更新）
        if d in out:
            out[d] = ("__DUP__",)
            continue
        out[d] = value
    return out


def sync_all_stocks_1day(
    stock_list_path: str,
    start_dt: datetime,
    end_dt: datetime,
    count: int,
    dry_run: bool = False,
    limit: int = 0,
    resume_from: str = "",
    sleep_seconds: float = 0.0,
) -> None:
    client: DzhRestClient = build_default_client()
    stocks = _load_stock_list(stock_list_path)
    if resume_from:
        resume_from = resume_from.strip().upper()
        # 找到 resume 起点（包含）
        idx = 0
        for i, s in enumerate(stocks):
            if s.code.strip().upper() == resume_from:
                idx = i
                break
        stocks = stocks[idx:]

    if limit and limit > 0:
        stocks = stocks[:limit]

    logger.info(
        "准备同步 1day 日线：股票数=%s 日期=%s~%s dry_run=%s",
        len(stocks),
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
        dry_run,
    )

    changed = 0
    same = 0
    failed = 0

    for i, s in enumerate(stocks, start=1):
        code = s.code.strip().upper()
        table = f"basic_data_{code.lower()}"
        try:
            api_map = _fetch_1day_map_from_api(client, code, start_dt, end_dt, count=count)
            conn = get_connection()
            try:
                _ensure_table_exists(conn, table)
                existing_map = _load_existing_1day_map(conn, table, "1day", start_dt, end_dt)

                if existing_map == api_map:
                    same += 1
                    logger.info("[%s/%s] %s 数据一致，跳过", i, len(stocks), code)
                else:
                    changed += 1
                    logger.info(
                        "[%s/%s] %s 数据不一致：DB=%s天 API=%s天，准备%s",
                        i,
                        len(stocks),
                        code,
                        len(existing_map),
                        len(api_map),
                        "覆盖更新" if not dry_run else "仅报告(dry-run)",
                    )
                    if not dry_run:
                        # 重新拉一次 bars 做写入（避免 map 丢失时间戳）
                        bars = client.fetch_kline(
                            obj=code,
                            period="1day",
                            begin_time=start_dt,
                            end_time=end_dt,
                            count=count,
                            split=1,
                        )
                        _save_bars_replace_range_1day(conn, table, "1day", bars, start_dt, end_dt)
            finally:
                conn.close()
        except Exception:
            failed += 1
            logger.exception("[%s/%s] %s 同步失败", i, len(stocks), code)

        if sleep_seconds and sleep_seconds > 0:
            import time

            time.sleep(sleep_seconds)

    logger.info("同步完成：一致=%s 不一致并处理=%s 失败=%s", same, changed, failed)


def fetch_and_store(
    obj: str,
    table: str,
    period: str,
    start_dt: datetime,
    end_dt: datetime,
    count: int,
) -> None:
    """Fetch K线并写入本地数据库."""
    client: DzhRestClient = build_default_client()

    logger.info(
        "开始拉取 %s %s (%s - %s)",
        obj,
        period,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    )
    bars = client.fetch_kline(
        obj=obj,
        period=period,
        begin_time=start_dt,
        end_time=end_dt,
        count=count,
        split=1,
    )
    logger.info("接口返回 %s 条记录", len(bars))

    conn = get_connection()
    try:
        try:
            saved = _save_bars(conn, table, period, bars)
            logger.info("写入表 %s 完成，记录数: %s", table, saved)
        except pymysql.err.OperationalError as exc:  # type: ignore[attr-defined]
            if exc.args and exc.args[0] == 1290:
                logger.error("数据库是只读实例，无法建表/写入，请切换到可写的本地库后再执行。", exc_info=True)
            else:
                raise
    finally:
        conn.close()


def parse_args() -> Dict[str, any]:
    defaults = _env_or_default()
    parser = argparse.ArgumentParser(description="拉取大智慧K线并写入本地DB")
    parser.add_argument("--obj", help="股票代码，如 SH601225", default=defaults["obj"])
    parser.add_argument(
        "--table",
        help="目标表名，默认 basic_data_<code小写>",
        default=None,
    )
    parser.add_argument("--period", help="周期，默认1day", default=defaults["period"])
    parser.add_argument(
        "--start", help="开始日期 yyyy-MM-dd", default=defaults["start"].strftime("%Y-%m-%d")
    )
    parser.add_argument(
        "--end", help="结束日期 yyyy-MM-dd", default=defaults["end"].strftime("%Y-%m-%d")
    )
    parser.add_argument("--count", help="拉取数量上限", type=int, default=defaults["count"])
    parser.add_argument(
        "--stock-list",
        help="股票列表csv（包含 code,name,nature 三列）",
        default=defaults["stock_list"],
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="按 stock-list 全量跑（仅同步 1day 指定日期范围，其他周期不动）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只对比不写库（用于先看有多少不一致）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="只跑前 N 个股票（调试用）",
    )
    parser.add_argument(
        "--resume-from",
        default="",
        help="从指定股票代码开始跑（包含该股票），例如 SH600000",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="每只股票之间 sleep 秒数（避免接口限流）",
    )
    args = parser.parse_args()

    start_dt = _parse_date(args.start)
    end_dt = _parse_date(args.end)
    table = args.table or f"basic_data_{args.obj.lower()}"

    return {
        "obj": args.obj,
        "table": table,
        "period": args.period,
        "start": start_dt,
        "end": end_dt,
        "count": args.count,
        "stock_list": args.stock_list,
        "all": args.all,
        "dry_run": args.dry_run,
        "limit": args.limit,
        "resume_from": args.resume_from,
        "sleep": args.sleep,
    }


if __name__ == "__main__":
    opts = parse_args()
    if opts.get("all"):
        # 全量：只同步 1day，且只更新该周期该日期范围
        sync_all_stocks_1day(
            stock_list_path=opts["stock_list"],
            start_dt=opts["start"],
            end_dt=opts["end"],
            count=opts["count"],
            dry_run=bool(opts.get("dry_run")),
            limit=int(opts.get("limit") or 0),
            resume_from=str(opts.get("resume_from") or ""),
            sleep_seconds=float(opts.get("sleep") or 0.0),
        )
    else:
        # 单股票（保留旧行为）
        fetch_and_store(
            obj=opts["obj"],
            table=opts["table"],
            period=opts["period"],
            start_dt=opts["start"],
            end_dt=opts["end"],
            count=opts["count"],
        )

