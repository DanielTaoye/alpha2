"""
从高分推荐(Redis)读取当日各股性Top5(共15只)股票，调用聚宽Alpha101因子并写入MySQL。

使用前请准备：
1) 设置聚宽账号密码环境变量：JQ_USERNAME / JQ_PASSWORD
2) 设置数据库环境变量（如有不同）：DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME/DB_TABLE
3) 确保安装依赖：pip install jqdatasdk sqlalchemy pymysql pandas numpy

运行方式（示例，Windows PowerShell 分步执行）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    python quant/fetch_alpha101_from_high_score.py
"""
import os
import sys
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import pymysql
from sqlalchemy import create_engine, text

# 后端路径，复用Redis配置与高分缓存服务
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from application.services.high_score_cache_service import HighScoreCacheService  # noqa: E402
from infrastructure.cache.redis_client import RedisClient  # noqa: E402

# 聚宽 SDK 放在后面导入，便于缺省安装时报出友好信息
try:
    # get_all_alpha_101 在 jqdatasdk.api 内定义，直接从顶层导入
    from jqdatasdk import auth, get_trade_days, get_all_alpha_101
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"导入 jqdatasdk 失败: {exc}；请先安装：pip install jqdatasdk") from exc


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
TABLE_NAME = os.getenv("DB_TABLE", "alpha101_factors")

MAX_PER_NATURE = 5
NATURES = ["短线", "波段", "中长线"]


# ---------------- 工具函数 ----------------
def _normalize_date_digits(val: str) -> str:
    digits = "".join(ch for ch in val if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits


def _jq_code(code: str) -> str:
    """尽量把 code 转为聚宽格式：6位 + .XSHG/XSHE"""
    raw = (code or "").strip().upper()
    if not raw:
        return ""

    # 处理包含分隔符的形式，如 600000.SH / 600000.SHZ / 000001.SZ / 000001.SZA
    for sep in [".", "-"]:
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) >= 2:
                left, right = parts[0], parts[1]
                if right.startswith("SH"):
                    return f"{left}.XSHG"
                if right.startswith("SZ"):
                    return f"{left}.XSHE"
            # 去掉分隔符后继续判断
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

    # 兜底：返回原值
    return raw


def _ensure_table(engine, table_name: str, alpha_cols: List[str]):
    """若表不存在则创建，包含101个alpha因子列与唯一键(date, stock_code)。"""
    with engine.begin() as conn:
        # 检查表是否已存在
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
        for col in alpha_cols:
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
    """获取已存在表的列名；不存在则返回空列表。"""
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
    """写入前删除同日同股票的旧记录，避免重复。"""
    if not codes:
        return
    placeholders = ", ".join([f":c{i}" for i in range(len(codes))])
    params = {f"c{i}": code for i, code in enumerate(codes)}
    params["d"] = date_str
    sql = f"DELETE FROM `{table_name}` WHERE `date`=:d AND `stock_code` IN ({placeholders})"
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def _auth_jq():
    if not JQ_USERNAME or not JQ_PASSWORD:
        raise SystemExit("请设置环境变量 JQ_USERNAME/JQ_PASSWORD 以使用聚宽数据。")
    auth(JQ_USERNAME, JQ_PASSWORD)


# ---------------- 主流程 ----------------
def fetch_top_from_redis(target_date: str) -> List[Dict]:
    """读取Redis高分榜，按股性各取Top5，返回列表。"""
    service = HighScoreCacheService()
    data = service.get_top_grouped_from_cache(limit_per_group=MAX_PER_NATURE, date_str=target_date, scan_limit=2000)
    groups: Dict[str, List[Dict]] = data.get("groups", {}) or {}
    stocks: List[Dict] = []
    for nature in NATURES:
        arr = groups.get(nature) or []
        for item in arr[:MAX_PER_NATURE]:
            stocks.append(item)
    return stocks


def fetch_alpha101_for_stocks(date_str: str, stocks: List[Dict]) -> pd.DataFrame:
    """调用聚宽获取Alpha101因子，返回带股票与股性信息的DataFrame。"""
    if not stocks:
        raise ValueError("无高分股票可用，无法获取因子。")

    # 选择交易日：若当日不是交易日，回退到最近的交易日
    trade_days = get_trade_days(start_date=date_str, end_date=date_str)
    if not len(trade_days):
        trade_days = get_trade_days(end_date=date_str, count=1)
    if not len(trade_days):
        raise ValueError(f"{date_str} 非交易日或获取交易日失败。")

    # 准备股票列表与映射
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

    # 取最近交易日
    trade_date = trade_days[-1].strftime("%Y-%m-%d")
    print(f"   交易日: {trade_date}, 请求标的: {jq_codes}")

    df = get_all_alpha_101(code=jq_codes, date=trade_date, alpha=None)
    if df is None or df.empty:
        raise ValueError(f"聚宽返回空数据：trade_date={trade_date}, codes={jq_codes}")

    df = df.reset_index()
    df.rename(columns={"index": "jq_code"}, inplace=True)
    df["date"] = trade_date
    df["stock_code"] = df["jq_code"].map(source_code_map)
    df["stock_name"] = df["jq_code"].map(name_map)
    df["nature"] = df["jq_code"].map(nature_map)
    df["source_date"] = date_str

    # 将缺失填为 None，避免 numpy NaN 进入数据库
    df = df.replace({np.nan: None})
    return df


def _iter_dates() -> List[str]:
    """返回需要处理的日期列表（YYYYMMDD）。优先读取环境变量 DATE_RANGE。"""
    date_range = os.getenv("DATE_RANGE", "").strip()
    if date_range:
        parts = [p.strip() for p in date_range.replace(",", " ").split() if p.strip()]
        return [_normalize_date_digits(p) for p in parts if _normalize_date_digits(p)]
    # 默认：仅当日
    return [_normalize_date_digits(datetime.now().strftime("%Y%m%d"))]


def main():
    date_list = _iter_dates()
    print(f"目标日期列表: {date_list}")

    print("1) 聚宽登录...")
    _auth_jq()
    print("   聚宽认证成功")

    engine = create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )

    total_written = 0
    alpha_cols_cached = None
    table_columns = _get_table_columns(engine, TABLE_NAME)
    table_exists = bool(table_columns)

    for target_date_digits in date_list:
        print(f"\n=== 处理日期 {target_date_digits} ===")
        print("  读取Redis高分榜...")
        stocks = fetch_top_from_redis(target_date_digits)
        print(f"  获取到 {len(stocks)} 只股票（{', '.join(NATURES)} 各取Top{MAX_PER_NATURE}）")

        print("  拉取Alpha101因子...")
        df = fetch_alpha101_for_stocks(target_date_digits, stocks)
        # jq_code 仅用于转换过程，避免写库失败
        if "jq_code" in df.columns:
            df = df.drop(columns=["jq_code"])
        alpha_cols = [col for col in df.columns if col.startswith("alpha_")]
        if alpha_cols_cached is None:
            alpha_cols_cached = alpha_cols
            _ensure_table(engine, TABLE_NAME, alpha_cols_cached)
            if not table_exists:
                table_columns = _get_table_columns(engine, TABLE_NAME)

        # 若表已存在且列不匹配，则仅写入交集列
        if table_columns:
            cols_to_use = [c for c in df.columns if c in table_columns]
            missing = [c for c in df.columns if c not in table_columns]
            if missing:
                print(f"  警告: 跳过未在表中存在的列 {missing}")
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

