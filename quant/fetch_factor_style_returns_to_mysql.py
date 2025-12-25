"""
把“风格因子暴露收益率”（get_factor_style_returns）写入 MySQL 新表：jq_factor_style_returns。

默认：
- 日期范围：DATE_RANGE（空格/逗号分隔 YYYYMMDD）；未设置则取当天
- 因子：STYLE_RETURNS_FACTORS（默认 'style'，表示全部风格因子）
- 市场范围：STYLE_RETURNS_UNIVERSE（默认 None=全市场；也可 hs300/zz500/zz800/zz1000/zz2000/zzqz）
- 行业：STYLE_RETURNS_INDUSTRY（默认 sw_l1）
- 数据库：默认 localhost:3306 / bendi（可用 DB_* 覆盖）

运行示例（PowerShell）：
    cd C:\\Users\\lenovo\\Desktop\\alpha_strategy_v2
    $env:DATE_RANGE="20241222 20241223 20241224 20241225"
    python quant/fetch_factor_style_returns_to_mysql.py
"""

import os
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from jqdatasdk import auth, get_factor_style_returns


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
TABLE_NAME = os.getenv("DB_TABLE_STYLE_RETURNS", "jq_factor_style_returns")


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
        `universe` VARCHAR(16) DEFAULT NULL,
        `industry` VARCHAR(16) NOT NULL,
        `value` DOUBLE DEFAULT NULL,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY `uniq_date_factor` (`date`, `factor_name`, `universe`, `industry`),
        INDEX `idx_date` (`date`),
        INDEX `idx_factor` (`factor_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))


def _delete_existing(engine, start_date: str, end_date: str, factors: List[str], universe: Optional[str], industry: str):
    if not factors:
        return
    placeholders = ", ".join([f":f{i}" for i in range(len(factors))])
    params = {f"f{i}": name for i, name in enumerate(factors)}
    params.update({"s": start_date, "e": end_date, "ind": industry})
    if universe is None or universe == "":
        sql = (
            f"DELETE FROM `{TABLE_NAME}` "
            f"WHERE `date` BETWEEN :s AND :e AND `industry`=:ind AND `universe` IS NULL "
            f"AND `factor_name` IN ({placeholders})"
        )
    else:
        params["u"] = universe
        sql = (
            f"DELETE FROM `{TABLE_NAME}` "
            f"WHERE `date` BETWEEN :s AND :e AND `industry`=:ind AND `universe`=:u "
            f"AND `factor_name` IN ({placeholders})"
        )
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def main():
    date_list = _iter_dates()
    start_date, end_date = _resolve_range(date_list)

    industry = os.getenv("STYLE_RETURNS_INDUSTRY", "sw_l1")
    universe = os.getenv("STYLE_RETURNS_UNIVERSE", "").strip() or None

    factors_env = os.getenv("STYLE_RETURNS_FACTORS", "style").strip()
    # 支持：'style' / 'style_pro' / 逗号分隔列表
    if "," in factors_env or " " in factors_env:
        factors = [x.strip() for x in factors_env.replace(",", " ").split() if x.strip()]
    else:
        factors = factors_env  # type: ignore[assignment]

    print(f"日期范围: {start_date} ~ {end_date}")
    print(f"industry: {industry}")
    print(f"universe: {universe}")
    print(f"factors: {factors_env}")

    print("1) 聚宽登录...")
    _auth()
    print("   聚宽认证成功")

    print("2) 拉取风格因子暴露收益率(get_factor_style_returns)...")
    df = get_factor_style_returns(
        factors=factors,
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        industry=industry,
    )
    if df is None or df.empty:
        raise ValueError("get_factor_style_returns 返回空")

    long_df = df.reset_index().melt(id_vars=["index"], var_name="factor_name", value_name="value")
    long_df = long_df.rename(columns={"index": "date"})
    long_df["universe"] = universe
    long_df["industry"] = industry
    long_df = long_df.replace({np.nan: None})

    factor_list_for_delete = sorted(long_df["factor_name"].dropna().astype(str).unique().tolist())

    print(f"3) 写入数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']} 表 {TABLE_NAME}")
    engine = create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    )
    _ensure_table(engine)
    _delete_existing(engine, start_date, end_date, factor_list_for_delete, universe, industry)
    long_df.to_sql(name=TABLE_NAME, con=engine, if_exists="append", index=False, chunksize=1000)

    print(f"完成：写入 {len(long_df)} 行到 {TABLE_NAME}")


if __name__ == "__main__":
    main()


