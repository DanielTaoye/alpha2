"""
诊断“回测里缺少某些C/R交易”的最小脚本：

典型现象：
- K线上能看到 C(触发日) / R(触发日)
- 但回测 trades 里没有这笔

常见原因：
回测定价规则使用“触发日后的次交易日开盘价”做买/卖价；
若数据库缺少该次交易日的 1day 数据（长假/数据未补齐），则交易会被跳过。

用法（PowerShell 分步执行，避免 &&）：
1) cd backend
2) python scripts/diagnose_backtest_missing_trades.py --table basic_data_sh601128
   或自定义：
   python scripts/diagnose_backtest_missing_trades.py --table basic_data_sh601128 --pairs 2024-02-07,2024-02-08 2024-09-30,2024-10-08
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Tuple, Optional

import pymysql

from infrastructure.persistence.database import DatabaseConnection
from domain.services.trading_calendar_service import TradingCalendarService


@dataclass
class DayRow:
    day: str
    exists_1day: bool
    first_ts: Optional[str] = None
    open_price: Optional[float] = None


def _query_1day_on_date(table: str, day_str: str) -> DayRow:
    with DatabaseConnection.get_connection_context() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            f"""
            SELECT shi_jian, kai_pan_jia
            FROM {table}
            WHERE peroid_type='1day'
              AND DATE(shi_jian) = %s
            ORDER BY shi_jian ASC
            LIMIT 1
            """,
            (day_str,),
        )
        row = cur.fetchone()
        if not row:
            return DayRow(day=day_str, exists_1day=False)
        return DayRow(
            day=day_str,
            exists_1day=True,
            first_ts=str(row.get("shi_jian")),
            open_price=float(row.get("kai_pan_jia")) if row.get("kai_pan_jia") is not None else None,
        )


def _query_first_1day_on_or_after(table: str, day_str: str) -> DayRow:
    start_ts = f"{day_str} 00:00:00"
    with DatabaseConnection.get_connection_context() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            f"""
            SELECT shi_jian, kai_pan_jia
            FROM {table}
            WHERE peroid_type='1day'
              AND shi_jian >= %s
            ORDER BY shi_jian ASC
            LIMIT 1
            """,
            (start_ts,),
        )
        row = cur.fetchone()
        if not row:
            return DayRow(day=day_str, exists_1day=False)
        return DayRow(
            day=day_str,
            exists_1day=True,
            first_ts=str(row.get("shi_jian")),
            open_price=float(row.get("kai_pan_jia")) if row.get("kai_pan_jia") is not None else None,
        )


def _next_trading_day_str(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    nxt: date = TradingCalendarService.get_next_trading_day(dt)
    return nxt.strftime("%Y-%m-%d")


def diagnose(table: str, pairs: List[Tuple[str, str]]) -> int:
    print(f"[diag] table={table}")
    cal = TradingCalendarService()
    _ = cal  # 强制加载日历

    for c_date, r_date in pairs:
        print("=" * 80)
        print(f"[pair] C={c_date}  R={r_date}")

        buy_plan = _next_trading_day_str(c_date)
        sell_plan = _next_trading_day_str(r_date)
        print(f"[plan] buy_exec(next trading day after C)  = {buy_plan}")
        print(f"[plan] sell_exec(next trading day after R) = {sell_plan}")

        # 精确日
        buy_exact = _query_1day_on_date(table, buy_plan)
        sell_exact = _query_1day_on_date(table, sell_plan)
        print(f"[db] buy_exact  DATE={buy_plan}  exists={buy_exact.exists_1day} ts={buy_exact.first_ts} open={buy_exact.open_price}")
        print(f"[db] sell_exact DATE={sell_plan} exists={sell_exact.exists_1day} ts={sell_exact.first_ts} open={sell_exact.open_price}")

        # 兜底：>= 计划日
        if not buy_exact.exists_1day:
            buy_fb = _query_first_1day_on_or_after(table, buy_plan)
            print(f"[db] buy_fallback  >= {buy_plan} exists={buy_fb.exists_1day} ts={buy_fb.first_ts} open={buy_fb.open_price}")
        if not sell_exact.exists_1day:
            sell_fb = _query_first_1day_on_or_after(table, sell_plan)
            print(f"[db] sell_fallback >= {sell_plan} exists={sell_fb.exists_1day} ts={sell_fb.first_ts} open={sell_fb.open_price}")

    print("=" * 80)
    print("[diag] done")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, help="K线表名，如 basic_data_sh601128")
    parser.add_argument(
        "--pairs",
        nargs="*",
        default=["2024-02-07,2024-02-08", "2024-09-30,2024-10-08"],
        help="C,R 日期对（逗号分隔），可传多个，例如 2024-02-07,2024-02-08 2024-09-30,2024-10-08",
    )
    args = parser.parse_args()

    pairs: List[Tuple[str, str]] = []
    for p in args.pairs:
        c, r = p.split(",", 1)
        pairs.append((c.strip(), r.strip()))

    raise SystemExit(diagnose(args.table, pairs))


if __name__ == "__main__":
    main()


