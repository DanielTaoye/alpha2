"""
从高分推荐(Redis)读取当日各股性Top5(共15只)股票，拉取“聚宽因子库”因子值（非Alpha101），写入MySQL新表。

使用前准备：
1) 安装依赖：pip install jqdatasdk sqlalchemy pymysql pandas numpy
2) 设置聚宽账号/密码（若未硬编码）：JQ_USERNAME / JQ_PASSWORD
3) 如需自定义库表：DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME/DB_TABLE_FACTORS
4) 日期范围可用环境变量 DATE_RANGE 指定，空格或逗号分隔（YYYYMMDD）；未设置则默认当天。

运行示例（PowerShell）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    $env:DATE_RANGE="20241222 20241223 20241224 20241225"
    python quant/fetch_factor_library_from_high_score.py
"""
import os
import sys
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import pymysql
from sqlalchemy import create_engine, text

# 复用 backend 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from application.services.high_score_cache_service import HighScoreCacheService  # noqa: E402

try:
    # 因子库接口在 jqdatasdk 内已提供：get_all_factors / get_factor_values
    from jqdatasdk import auth, get_trade_days, get_all_factors, get_factor_values
except ImportError as exc:
    raise SystemExit(
        f"缺少/无法导入 jqdatasdk 因子库接口: {exc}；请先安装：pip install jqdatasdk"
    ) from exc

# ---------------- 配置 ----------------
JQ_USERNAME = os.getenv("JQ_USERNAME", "17721044150")
JQ_PASSWORD = os.getenv("JQ_PASSWORD", "Taoye4675")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_NAME", "bendi"),
    "charset": "utf8mb4",
}
TABLE_NAME = os.getenv("DB_TABLE_FACTORS", "jq_factor_library")

MAX_PER_NATURE = 5
NATURES = ["短线", "波段", "中长线"]


# ---------------- 工具 ----------------
def _normalize_date_digits(val: str) -> str:
    digits = "".join(ch for ch in val if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits


def _jq_code(code: str) -> str:
    raw = (code or "").strip().upper()
    if not raw:
        return ""
    for sep in [".", "-"]:
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) >= 2:
                left, right = parts[0], parts[1]
                if right.startswith("SH"):
                    return f"{left}.XSHG"
                if right.startswith("SZ"):
                    return f"{left}.XSHE"
            raw = raw.replace(sep, "")
            break
    if raw.startswith("SH"):
        return f"{raw[2:]}.XSHG"
    if raw.startswith("SZ"):
        return f"{raw[2:]}.XSHE"
    if raw.startswith("6") and len(raw) >= 6:
        return f"{raw[:6]}.XSHG"
    if (raw.startswith("0") or raw.startswith("3")) and len(raw) >= 6:
        return f"{raw[:6]}.XSHE"
    return raw


def _auth_jq():
    if not JQ_USERNAME or not JQ_PASSWORD:
        raise SystemExit("请设置 JQ_USERNAME/JQ_PASSWORD")
    auth(JQ_USERNAME, JQ_PASSWORD)


def _ensure_table(engine, table_name: str, factor_cols: List[str]):
    """若表不存在则创建，包含因子列与唯一键(date, stock_code, factor_version)。"""
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=:db AND table_name=:tbl"
            ),
            {"db": DB_CONFIG["database"], "tbl": table_name},
        ).scalar()
        if exists:
            return

        cols_sql = []
        for col in factor_cols:
            cols_sql.append(f"`{col}` DOUBLE DEFAULT NULL")

        create_sql = f"""
        CREATE TABLE `{table_name}` (
            `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `date` DATE NOT NULL,
            `stock_code` VARCHAR(32) NOT NULL,
            `stock_name` VARCHAR(64),
            `nature` VARCHAR(16),
            `source_date` VARCHAR(16),
            {", ".join(cols_sql)},
            `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `uniq_date_code` (`date`, `stock_code`),
            INDEX `idx_date` (`date`),
            INDEX `idx_code` (`stock_code`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        conn.execute(text(create_sql))


def _get_table_columns(engine, table_name: str) -> List[str]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema=:db AND table_name=:tbl"
            ),
            {"db": DB_CONFIG["database"], "tbl": table_name},
        ).fetchall()
        return [r[0] for r in rows] if rows else []


def _delete_existing(engine, table_name: str, date_str: str, codes: List[str]):
    if not codes:
        return
    placeholders = ", ".join([f":c{i}" for i in range(len(codes))])
    params = {f"c{i}": code for i, code in enumerate(codes)}
    params["d"] = date_str
    sql = f"DELETE FROM `{table_name}` WHERE `date`=:d AND `stock_code` IN ({placeholders})"
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def fetch_top_from_redis(target_date: str) -> List[Dict]:
    service = HighScoreCacheService()
    data = service.get_top_grouped_from_cache(limit_per_group=MAX_PER_NATURE, date_str=target_date, scan_limit=2000)
    groups: Dict[str, List[Dict]] = data.get("groups", {}) or {}
    stocks: List[Dict] = []
    for nature in NATURES:
        arr = groups.get(nature) or []
        for item in arr[:MAX_PER_NATURE]:
            stocks.append(item)
    return stocks


def _iter_dates() -> List[str]:
    date_range = os.getenv("DATE_RANGE", "").strip()
    if date_range:
        parts = [p.strip() for p in date_range.replace(",", " ").split() if p.strip()]
        return [_normalize_date_digits(p) for p in parts if _normalize_date_digits(p)]
    return [_normalize_date_digits(datetime.now().strftime("%Y%m%d"))]


def fetch_factors_for_date(target_date_digits: str, factor_list: List[str], stocks: List[Dict]) -> pd.DataFrame:
    if not stocks:
        raise ValueError("无高分股票可用，无法获取因子。")

    trade_days = get_trade_days(start_date=target_date_digits, end_date=target_date_digits)
    if not len(trade_days):
        trade_days = get_trade_days(end_date=target_date_digits, count=1)
    if not len(trade_days):
        raise ValueError(f"{target_date_digits} 非交易日或获取交易日失败。")

    trade_date = trade_days[-1].strftime("%Y-%m-%d")

    jq_codes = []
    name_map = {}
    nature_map = {}
    source_code_map = {}
    for item in stocks:
        jq_code = _jq_code(item.get("stock_code", ""))
        if not jq_code:
            continue
        jq_codes.append(jq_code)
        name_map[jq_code] = item.get("stock_name", "")
        nature_map[jq_code] = item.get("nature", "")
        source_code_map[jq_code] = item.get("stock_code", "")

    if not jq_codes:
        raise ValueError("未能转换出有效的聚宽股票代码。")

    print(f"  交易日: {trade_date}, 请求标的: {jq_codes}")

    factor_dict = get_factor_values(
        securities=jq_codes,
        factors=factor_list,
        start_date=trade_date,
        end_date=trade_date,
    )

    rows = []
    for jq_code in jq_codes:
        row = {
            "date": trade_date,
            "stock_code": source_code_map.get(jq_code),
            "stock_name": name_map.get(jq_code),
            "nature": nature_map.get(jq_code),
            "source_date": target_date_digits,
        }
        for fac in factor_list:
            df = factor_dict.get(fac)
            if df is None or df.empty:
                row[fac] = None
                continue
            val = df.loc[pd.to_datetime(trade_date), jq_code]
            row[fac] = None if pd.isna(val) else float(val)
        rows.append(row)

    return pd.DataFrame(rows)


def main():
    date_list = _iter_dates()
    print(f"目标日期列表: {date_list}")

    print("1) 聚宽登录...")
    _auth_jq()
    print("   聚宽认证成功")

    print("2) 拉取因子列表...")
    all_factors_df = get_all_factors()
    factor_list = all_factors_df["factor"].tolist()
    print(f"   因子数量: {len(factor_list)}")

    engine = create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )

    table_columns = _get_table_columns(engine, TABLE_NAME)
    table_exists = bool(table_columns)
    total_written = 0
    factor_cols_cached = None

    for target_date_digits in date_list:
        print(f"\n=== 处理日期 {target_date_digits} ===")
        print("  读取Redis高分榜...")
        stocks = fetch_top_from_redis(target_date_digits)
        print(f"  获取到 {len(stocks)} 只股票（{', '.join(NATURES)} 各取Top{MAX_PER_NATURE}）")

        print("  拉取聚宽因子库因子...")
        df = fetch_factors_for_date(target_date_digits, factor_list, stocks)

        if factor_cols_cached is None:
            # 确保表存在；若已存在且列不匹配，后续会做交集
            factor_cols_cached = factor_list
            _ensure_table(engine, TABLE_NAME, factor_cols_cached)
            if not table_exists:
                table_columns = _get_table_columns(engine, TABLE_NAME)

        if table_columns:
            cols_to_use = [c for c in df.columns if c in table_columns]
            missing = [c for c in df.columns if c not in table_columns]
            if missing:
                print(f"  警告: 跳过未在表中存在的列 {missing[:10]}{'...' if len(missing)>10 else ''}")
            df = df[cols_to_use]

        print("  写入数据库...")
        _delete_existing(engine, TABLE_NAME, df["date"].iloc[0], df["stock_code"].tolist())
        df.to_sql(name=TABLE_NAME, con=engine, if_exists="append", index=False, chunksize=200)
        total_written += len(df)
        print(f"  日期 {df['date'].iloc[0]} 写入 {len(df)} 行")

    print(f"\n完成：共写入 {total_written} 行到 {TABLE_NAME}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"执行失败: {exc}")

