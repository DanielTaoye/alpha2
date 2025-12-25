"""
把“因子看板分位数历史收益率”（get_factor_stats）写入 MySQL 新表：jq_factor_stats。

默认：
- 日期范围：读取环境变量 DATE_RANGE（空格/逗号分隔 YYYYMMDD）；未设置则取当天
- 因子：默认取 get_all_factors() 中 category == 'style' 的因子（通常约10个）
- 股票池：UNIVERSE_TYPE（默认 hs300）
- 手续费：COMMISION_FEE（默认 0.0，可选 0.0/0.0008/0.0018）
- 数据库：默认 localhost:3306 / bendi（可用 DB_* 覆盖）

运行示例（PowerShell）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    $env:DATE_RANGE="20241222 20241223 20241224 20241225"
    python quant/fetch_factor_stats_to_mysql.py
"""

import os
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from jqdatasdk import auth, get_all_factors, get_factor_stats


# ---------- 聚宽账号（默认硬编码，可用环境变量覆盖） ----------
JQ_USERNAME = os.getenv("JQ_USERNAME", "17721044150")
JQ_PASSWORD = os.getenv("JQ_PASSWORD", "Taoye4675")


# ---------- DB 配置（默认硬编码，可用环境变量覆盖） ----------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_NAME", "bendi"),
    "charset": "utf8mb4",
}
TABLE_NAME = os.getenv("DB_TABLE_FACTOR_STATS", "jq_factor_stats")


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
        return [_normalize_date_digits(p) for p in parts if _normalize_date_digits(p)]
    return [_normalize_date_digits(datetime.now().strftime("%Y%m%d"))]


def _resolve_range(date_list: List[str]) -> tuple[str, str]:
    if not date_list:
        raise ValueError("DATE_RANGE 为空")
    start = min(date_list)
    end = max(date_list)
    return _digits_to_date_str(start), _digits_to_date_str(end)


def _auth():
    if not JQ_USERNAME or not JQ_PASSWORD:
        raise SystemExit("请设置 JQ_USERNAME/JQ_PASSWORD")
    auth(JQ_USERNAME, JQ_PASSWORD)


def _ensure_table(engine):
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS `{TABLE_NAME}` (
        `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
        `date` DATE NOT NULL,
        `factor_name` VARCHAR(64) NOT NULL,
        `universe_type` VARCHAR(16) NOT NULL,
        `commision_fee` DOUBLE NOT NULL,
        `q1` DOUBLE DEFAULT NULL,
        `q2` DOUBLE DEFAULT NULL,
        `q3` DOUBLE DEFAULT NULL,
        `q4` DOUBLE DEFAULT NULL,
        `q5` DOUBLE DEFAULT NULL,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY `uniq_date_factor` (`date`, `factor_name`, `universe_type`, `commision_fee`),
        INDEX `idx_date` (`date`),
        INDEX `idx_factor` (`factor_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))


def _delete_existing(engine, start_date: str, end_date: str, factor_names: List[str], universe_type: str, commision_fee: float):
    if not factor_names:
        return
    placeholders = ", ".join([f":f{i}" for i in range(len(factor_names))])
    params = {f"f{i}": name for i, name in enumerate(factor_names)}
    params.update({"s": start_date, "e": end_date, "u": universe_type, "c": commision_fee})
    sql = (
        f"DELETE FROM `{TABLE_NAME}` "
        f"WHERE `date` BETWEEN :s AND :e AND `universe_type`=:u AND `commision_fee`=:c "
        f"AND `factor_name` IN ({placeholders})"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def _default_factor_names() -> List[str]:
    df = get_all_factors()
    if df is None or df.empty:
        raise ValueError("get_all_factors 返回空")
    # 默认：只取风格因子（style）
    style_df = df[df["category"] == "style"]
    names = style_df["factor"].dropna().astype(str).tolist()
    if not names:
        # 兜底：如果没有 style 分类，就取前 10 个
        names = df["factor"].dropna().astype(str).head(10).tolist()
    return names


def main():
    date_list = _iter_dates()
    start_date, end_date = _resolve_range(date_list)

    universe_type = os.getenv("UNIVERSE_TYPE", "hs300")
    commision_fee = float(os.getenv("COMMISION_FEE", "0.0"))

    print(f"日期范围: {start_date} ~ {end_date}")
    print(f"股票池(universe_type): {universe_type}")
    print(f"手续费(commision_fee): {commision_fee}")

    print("1) 聚宽登录...")
    _auth()
    print("   聚宽认证成功")

    factor_names_env = os.getenv("FACTOR_STATS_NAMES", "").strip()
    if factor_names_env:
        factor_names = [x.strip() for x in factor_names_env.replace(",", " ").split() if x.strip()]
    else:
        factor_names = _default_factor_names()
    print(f"2) 因子数量: {len(factor_names)}")

    print("3) 拉取因子看板分位数历史收益率(get_factor_stats)...")
    data = get_factor_stats(
        factor_names=factor_names,
        universe_type=universe_type,
        start_date=start_date,
        end_date=end_date,
        skip_paused=False,
        commision_fee=commision_fee,
    )
    if not data:
        raise ValueError("get_factor_stats 返回空")

    rows = []
    for name, df in data.items():
        if df is None or df.empty:
            continue
        tmp = df.copy()
        tmp = tmp.reset_index().rename(columns={"index": "date"})
        # 列名可能是 int: 1..5
        rename_map = {1: "q1", 2: "q2", 3: "q3", 4: "q4", 5: "q5", "1": "q1", "2": "q2", "3": "q3", "4": "q4", "5": "q5"}
        tmp = tmp.rename(columns=rename_map)
        for col in ["q1", "q2", "q3", "q4", "q5"]:
            if col not in tmp.columns:
                tmp[col] = None
        tmp["factor_name"] = name
        tmp["universe_type"] = universe_type
        tmp["commision_fee"] = commision_fee
        tmp = tmp[["date", "factor_name", "universe_type", "commision_fee", "q1", "q2", "q3", "q4", "q5"]]
        rows.append(tmp)

    if not rows:
        raise ValueError("无可写入的数据（全部因子为空）")

    out = pd.concat(rows, ignore_index=True)
    out = out.replace({np.nan: None})

    print(f"4) 写入数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']} 表 {TABLE_NAME}")
    engine = create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )
    _ensure_table(engine)
    _delete_existing(engine, start_date, end_date, factor_names, universe_type, commision_fee)
    out.to_sql(name=TABLE_NAME, con=engine, if_exists="append", index=False, chunksize=500)

    print(f"完成：写入 {len(out)} 行到 {TABLE_NAME}")


if __name__ == "__main__":
    main()


