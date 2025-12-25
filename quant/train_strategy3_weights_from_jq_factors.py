"""
用 bendi.jq_factor_library（聚宽因子库因子值）+ 次日收益，计算每个因子的 RankIC / IR，并导出权重文件供“策略3 聚宽概率”使用。

假设：
- jq_factor_library: 每行一只股票一天，列包含若干因子（约260列），列名=因子code
- K线表: basic_data_{stock_code.lower()}，包含 time, close 等字段（与现有项目一致）

输出：
- quant/strategy3_factor_weights.json （默认）

运行示例（PowerShell）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    $env:DATE_RANGE="20241222 20241223 20241224 20241225"
    python quant/train_strategy3_weights_from_jq_factors.py
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_NAME", "bendi"),
    "charset": "utf8mb4",
}

FACTOR_TABLE = os.getenv("DB_TABLE_FACTORS", "jq_factor_library")
OUTPUT_PATH = os.getenv("STRATEGY3_WEIGHTS_OUT", os.path.join("quant", "strategy3_factor_weights.json"))

# 行情只读库（用于计算 forward returns）
READONLY_DB_CONFIG = {
    "host": os.getenv("READONLY_DB_HOST", ""),
    "port": int(os.getenv("READONLY_DB_PORT", "25924")),
    "user": os.getenv("READONLY_DB_USER", "root"),
    "password": os.getenv("READONLY_DB_PASSWORD", "MrEPYZus7myr"),
    # 你提供的只读库 schema：stock（也可用环境变量覆盖）
    "database": os.getenv("READONLY_DB_NAME", "stock"),
    "charset": os.getenv("READONLY_DB_CHARSET", "utf8mb4"),
}

# 预测窗口：次日收益（T+1）
FORWARD_DAYS = int(os.getenv("FORWARD_DAYS", "1"))

# 因子筛选阈值
MIN_NON_NULL_RATIO = float(os.getenv("MIN_NON_NULL_RATIO", "0.6"))
MIN_DAYS = int(os.getenv("MIN_DAYS", "2"))


def _normalize_date_digits(val: str) -> str:
    digits = "".join(ch for ch in str(val) if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits


def _digits_to_date_str(digits: str) -> str:
    d = _normalize_date_digits(digits)
    if len(d) != 8:
        raise ValueError(f"日期格式不对: {digits}")
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"


def _iter_dates() -> List[str]:
    date_range = os.getenv("DATE_RANGE", "").strip()
    if date_range:
        parts = [p.strip() for p in date_range.replace(",", " ").split() if p.strip()]
        return sorted({_normalize_date_digits(p) for p in parts if _normalize_date_digits(p)})
    return [_normalize_date_digits(datetime.now().strftime("%Y%m%d"))]


def _engine():
    return create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )


def _engine_readonly():
    """只读行情库连接（用于取 basic_data_* close）。"""
    if not READONLY_DB_CONFIG["host"] or not READONLY_DB_CONFIG["user"] or not READONLY_DB_CONFIG["password"] or not READONLY_DB_CONFIG["database"]:
        raise ValueError(
            "未配置只读行情库连接，请设置环境变量 READONLY_DB_HOST/READONLY_DB_PORT/READONLY_DB_USER/READONLY_DB_PASSWORD（READONLY_DB_NAME 默认为 stock）"
        )
    eng = create_engine(
        f"mysql+pymysql://{READONLY_DB_CONFIG['user']}:{READONLY_DB_CONFIG['password']}@"
        f"{READONLY_DB_CONFIG['host']}:{READONLY_DB_CONFIG['port']}/{READONLY_DB_CONFIG['database']}?charset={READONLY_DB_CONFIG['charset']}"
    )
    # 连接自检，避免后续吞异常导致“查不到数据”难定位
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        raise ValueError(f"只读行情库连接失败: {e}") from e
    return eng


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


def _load_factor_panel(engine, start_date: str, end_date: str) -> pd.DataFrame:
    # 读取全量列可能很宽，但日期窗口通常不大；这里直接 select *（你也可以按需裁剪因子列）
    sql = text(f"SELECT * FROM `{FACTOR_TABLE}` WHERE `date` BETWEEN :s AND :e")
    df = pd.read_sql(sql, engine, params={"s": start_date, "e": end_date})
    if df.empty:
        raise ValueError(f"{FACTOR_TABLE} 在 {start_date}~{end_date} 无数据")
    # 统一 date 为 YYYY-MM-DD
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def _fetch_close_series(engine, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    table = f"basic_data_{stock_code.lower()}"
    # 只读库字段名可能不是 time/date，这里自动探测一个“日期列”
    schema = READONLY_DB_CONFIG.get("database") or ""

    # 缓存：避免每只股票都扫 information_schema
    if not hasattr(_fetch_close_series, "_col_cache"):
        setattr(_fetch_close_series, "_col_cache", {})
    col_cache: Dict[str, Optional[str]] = getattr(_fetch_close_series, "_col_cache")

    date_col = col_cache.get(f"{table}::date")
    close_col = col_cache.get(f"{table}::close")
    period_col = col_cache.get(f"{table}::period")
    if date_col is None:
        try:
            sql_cols = text(
                "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.columns "
                "WHERE table_schema=:db AND table_name=:tbl"
            )
            cols_df = pd.read_sql(sql_cols, engine, params={"db": schema, "tbl": table})
            if cols_df.empty:
                col_cache[f"{table}::date"] = None
                col_cache[f"{table}::close"] = None
                col_cache[f"{table}::period"] = None
                return pd.DataFrame(columns=["d", "c"])

            # 优先顺序：常见日期列名优先，其次选 date/datetime/timestamp 类型的第一列
            preferred = [
                "shi_jian", "time", "date", "datetime", "dt", "trade_date", "trade_time",
                "day", "t", "time_key", "date_key", "timestamp",
            ]
            name_set = {str(x).lower(): str(x) for x in cols_df["COLUMN_NAME"].tolist()}
            chosen = None
            for key in preferred:
                if key in name_set:
                    chosen = name_set[key]
                    break
            if not chosen:
                cand = cols_df[cols_df["DATA_TYPE"].isin(["date", "datetime", "timestamp"])].copy()
                if not cand.empty:
                    chosen = str(cand.iloc[0]["COLUMN_NAME"])

            # close 列名探测
            close_preferred = ["shou_pan_jia", "close", "close_price", "close_px", "shoupan", "spj"]
            close_chosen = None
            for key in close_preferred:
                if key in name_set:
                    close_chosen = name_set[key]
                    break

            # 周期列探测（你的库里是 peroid_type）
            period_preferred = ["peroid_type", "period_type", "period"]
            period_chosen = None
            for key in period_preferred:
                if key in name_set:
                    period_chosen = name_set[key]
                    break

            col_cache[f"{table}::date"] = chosen
            col_cache[f"{table}::close"] = close_chosen
            col_cache[f"{table}::period"] = period_chosen
            date_col = chosen
            close_col = close_chosen
            period_col = period_chosen
        except Exception as e:
            if os.getenv("DEBUG_SQL", "0") == "1":
                print(f"[DEBUG] information_schema failed: table={table}, err={e}")
            col_cache[f"{table}::date"] = None
            col_cache[f"{table}::close"] = None
            col_cache[f"{table}::period"] = None
            return pd.DataFrame(columns=["d", "c"])

    if not date_col or not close_col:
        return pd.DataFrame(columns=["d", "c"])

    try:
        where_period = ""
        # 只取日线：你的表是 6=1day
        if period_col:
            where_period = f" AND `{period_col}` IN ('6','1day','day','1d',6)"
        sql_px = text(
            f"SELECT DATE(`{date_col}`) AS d, `{close_col}` AS c FROM `{table}` "
            f"WHERE DATE(`{date_col}`) BETWEEN :s AND :e{where_period} ORDER BY `{date_col}`"
        )
        df = pd.read_sql(sql_px, engine, params={"s": start_date, "e": end_date})
        if df.empty:
            return df
        df["d"] = pd.to_datetime(df["d"]).dt.strftime("%Y-%m-%d")
        return df
    except Exception as e:
        if os.getenv("DEBUG_SQL", "0") == "1":
            print(
                f"[DEBUG] query detected cols failed: table={table}, date_col={date_col}, close_col={close_col}, period_col={period_col}, err={e}"
            )
        return pd.DataFrame(columns=["d", "c"])
    if df.empty:
        return df
    df["d"] = pd.to_datetime(df["d"]).dt.strftime("%Y-%m-%d")
    return df


def _build_forward_returns(engine, stock_codes: List[str], dates: List[str], forward_days: int) -> pd.DataFrame:
    """
    返回 DataFrame: columns = ['date','stock_code','ret_fwd']
    ret_fwd 为从 date 到 date+forward_days 的收益（按交易日序列下一条/下N条 close）
    """
    if not stock_codes:
        raise ValueError("stock_codes 为空")
    start_date = min(dates)
    # 多取几天以便拿到 forward close
    end_date = max(dates)

    rows = []
    missing_tables = 0
    for code in stock_codes:
        px = _fetch_close_series(engine, code, start_date, end_date)
        if px.empty:
            missing_tables += 1
            continue
        px = px.dropna()
        px = px.drop_duplicates(subset=["d"], keep="last").reset_index(drop=True)
        px["c_fwd"] = px["c"].shift(-forward_days)
        px["ret_fwd"] = (px["c_fwd"] / px["c"]) - 1.0
        out = px[["d", "ret_fwd"]].rename(columns={"d": "date"})
        out["stock_code"] = code
        rows.append(out)
    if not rows:
        raise ValueError(f"无法从K线表构建 forward returns（可能缺数据/表不存在）。样本股票={len(stock_codes)}，无数据股票={missing_tables}")
    df = pd.concat(rows, ignore_index=True)
    df = df[df["date"].isin(dates)]
    return df


def _spearman_ic(x: pd.Series, y: pd.Series) -> Optional[float]:
    tmp = pd.concat([x, y], axis=1).dropna()
    if len(tmp) < 3:
        return None
    return float(tmp.iloc[:, 0].rank().corr(tmp.iloc[:, 1].rank(), method="pearson"))


def main():
    date_digits = _iter_dates()
    start_date = _digits_to_date_str(min(date_digits))
    end_date = _digits_to_date_str(max(date_digits))

    print(f"训练日期范围: {start_date} ~ {end_date}（{len(date_digits)}天）")
    eng = _engine()
    eng_ro = _engine_readonly()

    df = _load_factor_panel(eng, start_date, end_date)
    stock_codes = sorted(df["stock_code"].dropna().astype(str).unique().tolist())
    dates = sorted(df["date"].dropna().astype(str).unique().tolist())

    print(f"样本股票数: {len(stock_codes)}，样本交易日数(因子表): {len(dates)}")

    # forward returns 从只读行情库取
    rets = _build_forward_returns(eng_ro, stock_codes, dates, FORWARD_DAYS)
    merged = df.merge(rets, on=["date", "stock_code"], how="inner")
    if merged.empty:
        raise ValueError("因子表与收益无法对齐（date/stock_code 不匹配）")

    # 确定因子列：排除元字段
    meta_cols = {
        "id", "date", "stock_code", "stock_name", "nature", "source_date",
        "created_at", "updated_at",
    }
    all_cols = set(merged.columns)
    factor_cols = [c for c in merged.columns if c not in meta_cols and c not in {"ret_fwd"}]

    # 数值列过滤
    numeric_factors = []
    for c in factor_cols:
        if pd.api.types.is_numeric_dtype(merged[c]) or merged[c].dtype == object:
            numeric_factors.append(c)
    factor_cols = numeric_factors

    print(f"候选因子数: {len(factor_cols)}")

    ic_series: Dict[str, List[float]] = {f: [] for f in factor_cols}

    # 按天算 cross-sectional IC
    for d in dates:
        day = merged[merged["date"] == d]
        if len(day) < 5:
            continue
        y = day["ret_fwd"]
        for f in factor_cols:
            # 非空比例筛选（按天）
            non_null_ratio = day[f].notna().mean()
            if non_null_ratio < MIN_NON_NULL_RATIO:
                continue
            ic = _spearman_ic(day[f], y)
            if ic is not None and not np.isnan(ic):
                ic_series[f].append(ic)

    rows = []
    for f, ics in ic_series.items():
        if len(ics) < MIN_DAYS:
            continue
        ic_mean = float(np.mean(ics))
        ic_std = float(np.std(ics, ddof=1)) if len(ics) > 1 else 0.0
        ir = float(ic_mean / ic_std) if ic_std > 0 else 0.0
        rows.append({"factor": f, "ic_mean": ic_mean, "ic_std": ic_std, "ir": ir, "n_days": len(ics)})

    if not rows:
        raise ValueError("没有足够的因子可以计算 IC/IR（可能历史太短或缺失太多）")

    stats = pd.DataFrame(rows).sort_values("ir", ascending=False)
    print("Top 20 因子（按 IR 排序）：")
    print(stats.head(20).to_string(index=False))

    # 权重：只取 IR>0 的因子，按 IR 归一化
    pos = stats[stats["ir"] > 0].copy()
    if pos.empty:
        raise ValueError("所有因子 IR<=0，无法生成正权重（历史太短/噪声大）")
    pos["weight"] = pos["ir"] / pos["ir"].sum()

    payload = {
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_range": {"start": start_date, "end": end_date},
        "forward_days": FORWARD_DAYS,
        "min_non_null_ratio": MIN_NON_NULL_RATIO,
        "min_days": MIN_DAYS,
        "factor_count_total": int(len(factor_cols)),
        "factor_count_weighted": int(len(pos)),
        "weights": {r["factor"]: float(r["weight"]) for r in pos.to_dict(orient="records")},
        "stats": stats.to_dict(orient="records"),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"权重已写入: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()


