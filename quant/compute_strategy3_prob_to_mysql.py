"""
把策略3“聚宽概率”写入本地 bendi 新表：strategy3_probabilities

流程：
1) 读取 quant/strategy3_factor_weights.json
2) 从 bendi.jq_factor_library 取指定日期的因子值（建议先跑 quant/fetch_factor_library_from_high_score.py 写入当天数据）
3) 按因子做横截面 z-score，加权求和得到 raw_score，再 sigmoid -> prob
4) 写入 bendi.strategy3_probabilities（upsert by date+stock_code）

运行示例（PowerShell）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    $env:DATE_RANGE="20251225"
    python quant/compute_strategy3_prob_to_mysql.py
"""

import json
import math
import os
from datetime import datetime
from typing import Dict, List

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
OUT_TABLE = os.getenv("DB_TABLE_STRATEGY3", "strategy3_probabilities")
WEIGHTS_PATH = os.getenv("STRATEGY3_WEIGHTS_PATH", os.path.join("quant", "strategy3_factor_weights.json"))


def _normalize_date_digits(val: str) -> str:
    digits = "".join(ch for ch in str(val) if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits


def _digits_to_date_str(digits: str) -> str:
    d = _normalize_date_digits(digits)
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"


def _iter_dates() -> List[str]:
    date_range = os.getenv("DATE_RANGE", "").strip()
    if date_range:
        parts = [p.strip() for p in date_range.replace(",", " ").split() if p.strip()]
        return sorted({_normalize_date_digits(p) for p in parts if _normalize_date_digits(p)})
    return [_normalize_date_digits(datetime.now().strftime("%Y%m%d"))]


def _sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _engine():
    return create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )


def _ensure_table(engine):
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{OUT_TABLE}` (
        `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
        `date` DATE NOT NULL,
        `source_date` VARCHAR(16) DEFAULT NULL,
        `stock_code` VARCHAR(32) NOT NULL,
        `prob` DOUBLE DEFAULT NULL,
        `raw` DOUBLE DEFAULT NULL,
        `used_factors` INT DEFAULT 0,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY `uniq_date_code` (`date`, `stock_code`),
        INDEX `idx_source_date` (`source_date`),
        INDEX `idx_date` (`date`),
        INDEX `idx_code` (`stock_code`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(sql))
        # 兼容旧表：如果已存在但缺少 source_date，就自动补齐
        cols = conn.execute(text(f"SHOW COLUMNS FROM `{OUT_TABLE}`")).fetchall()
        col_names = {str(r[0]) for r in cols}
        if "source_date" not in col_names:
            conn.execute(text(f"ALTER TABLE `{OUT_TABLE}` ADD COLUMN `source_date` VARCHAR(16) DEFAULT NULL AFTER `date`"))
            conn.execute(text(f"CREATE INDEX `idx_source_date` ON `{OUT_TABLE}` (`source_date`)"))


def _load_weights() -> Dict[str, float]:
    if not os.path.exists(WEIGHTS_PATH):
        raise ValueError(f"权重文件不存在: {WEIGHTS_PATH}")
    with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    weights = payload.get("weights") or {}
    if not isinstance(weights, dict) or not weights:
        raise ValueError("权重文件 weights 为空/格式不对")
    return {str(k): float(v) for k, v in weights.items()}


def main():
    dates = _iter_dates()
    weights = _load_weights()
    engine = _engine()
    _ensure_table(engine)

    for d_digits in dates:
        d = _digits_to_date_str(d_digits)
        print(f"处理日期: {d}")
        df = pd.read_sql(
            text(f"SELECT * FROM `{FACTOR_TABLE}` WHERE `date`=:d"),
            engine,
            params={"d": d},
        )
        # 若按 date 无数据，则按 source_date 回退（因为 fetch_factor_library_from_high_score 可能回退到最近交易日）
        if df.empty:
            df = pd.read_sql(
                text(f"SELECT * FROM `{FACTOR_TABLE}` WHERE `source_date`=:sd"),
                engine,
                params={"sd": d_digits},
            )
        if df.empty:
            print(f"  跳过：{FACTOR_TABLE} 无数据（date/source_date都没命中）")
            continue

        # 以实际拉到的数据日期为准（可能与 source_date 不同）
        actual_date = pd.to_datetime(df['date'].iloc[0]).strftime("%Y-%m-%d") if 'date' in df.columns else d

        # 只保留权重因子中存在于表里的列
        factor_cols = [c for c in weights.keys() if c in df.columns]
        if not factor_cols:
            print("  跳过：因子表中没有任何权重因子列")
            continue

        # 横截面 z-score
        z_df = df[factor_cols].apply(pd.to_numeric, errors="coerce")
        mu = z_df.mean(axis=0, skipna=True)
        std = z_df.std(axis=0, skipna=True, ddof=1).replace({0.0: np.nan})
        z = (z_df - mu) / std

        w = pd.Series({k: weights[k] for k in factor_cols})
        used = z.notna().mul(w.ne(0), axis=1).sum(axis=1)  # 近似统计使用的因子数
        raw = z.mul(w, axis=1).sum(axis=1, skipna=True)
        # pandas 对“全NaN行”的 sum 会给 0，这会导致 prob=0.5 误导；这里显式置空
        raw = raw.where(used > 0, np.nan)

        out = pd.DataFrame(
            {
                "date": pd.to_datetime(actual_date),
                "source_date": str(d_digits),
                "stock_code": df["stock_code"].astype(str),
                "prob": raw.apply(lambda x: _sigmoid(float(x)) if pd.notna(x) else None),
                "raw": raw.replace({np.nan: None}),
                "used_factors": used.fillna(0).astype(int),
            }
        )

        # upsert：先删再插（简单可靠）
        code_list = out["stock_code"].tolist()
        if code_list:
            placeholders = ", ".join([f":c{i}" for i in range(len(code_list))])
            params = {f"c{i}": code for i, code in enumerate(code_list)}
            params["d"] = actual_date
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM `{OUT_TABLE}` WHERE `date`=:d AND `stock_code` IN ({placeholders})"), params)

        out.to_sql(name=OUT_TABLE, con=engine, if_exists="append", index=False, chunksize=500)
        print(f"  写入 {len(out)} 行到 {OUT_TABLE}")


if __name__ == "__main__":
    main()


