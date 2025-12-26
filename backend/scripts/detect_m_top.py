"""
M头形态扫描脚本

用途：
- 批量扫描股票，从指定起始日期(默认 2024-01-01)到今天，判断是否满足“M头”条件
- 输出：股票代码 + 触发日期(按“今天”为触发日) + X/Y/Z 三个关键日期 + 关键数值

M头逻辑（按用户描述）：
Step1: 对每个“今天”t，向前取5个交易日窗口 [t-4..t]。
       今天和昨日的收盘价都不可以是这5天收盘价中的最大值日。
       在该窗口中找到收盘价最大的日期，设为 X日。

Step2: 从 X日 向前找3日 (X-3..X-1)：
       - X日的收盘价 和 最高价 均大于前三日对应值
       - 且“前三日的收盘价到X日最高价”涨幅全部 > 5%

Step3: 从 X日 向前至多找5日 (X-5..X-1)，找到这5日内“收盘价最低”的日子为 Y日。
       - X日收盘价 > Y日最高价，且涨幅 > 5%

Step4: 从 Y日 向前至多找5日 (Y-5..Y-1)，找到这5日内“最高价最高”的日子为 Z日。
       - Z日收盘价 > Y日收盘价，且涨幅 > 5%

Step5: Z日最高价 > X日最高价
Step6: Z日成交量 > X日成交量

用法示例：
    python backend/scripts/detect_m_top.py --stocks SZ300188 SH603556
    python backend/scripts/detect_m_top.py --stocks-file .\\stocks.txt
    python backend/scripts/detect_m_top.py --start 2024-01-01 --end 2025-12-26 --out m_top.csv

说明：
- 本脚本不输出任何 emoji。
- 数据来源：MySQL 中 `basic_data_{code.lower()}` 表，`peroid_type='1day'` 的日线数据。
"""

import sys
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Sequence, Tuple
import argparse
import csv
import logging

# 控制台输出强制使用UTF-8
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.persistence.database import DatabaseConnection

# 避免各业务模块 logger 混入控制台输出
logging.disable(logging.CRITICAL)


DEFAULT_STOCKS = [
    "SZ300188",
    "SH603556",
    "SZ002130",
    "SH600037",
    "SZ301039",
    "SZ300058",
    "SZ300768",
    "SH688536",
    "SH600458",
    "SZ002065",
    "SH603327",
    "SZ300564",
    "SH603298",
    "SZ002387",
    "SH600518",
    "SH600256",
    "SH603486",
    "SH603588",
    "SZ000786",
    "SH600179",
]


def _as_date_str(d: Any) -> str:
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d).split(" ")[0].strip()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _pct_up(a: float, b: float) -> float:
    """(a-b)/b * 100. b<=0 时返回0"""
    if b <= 0:
        return 0.0
    return (a - b) / b * 100.0


def load_daily_kline_series(
    stock_code: str, start_date: str, end_date: str
) -> List[Dict[str, Any]]:
    """
    从K线表读取日线：date/close/high/volume
    返回按日期升序排列的列表。
    """
    code = (stock_code or "").strip().upper()
    if not code:
        return []
    table_name = f"basic_data_{code.lower()}"
    with DatabaseConnection.get_connection_context() as conn:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        sql = f"""
            SELECT
                DATE(shi_jian) AS trade_date,
                shou_pan_jia AS close_price,
                zui_gao_jia AS high_price,
                cheng_jiao_liang AS volume
            FROM `{table_name}`
            WHERE peroid_type = '1day'
              AND DATE(shi_jian) >= %s
              AND DATE(shi_jian) <= %s
            ORDER BY shi_jian ASC
        """
        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall() or []

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "date": _as_date_str(r.get("trade_date")),
                "close": _safe_float(r.get("close_price")),
                "high": _safe_float(r.get("high_price")),
                "volume": _safe_float(r.get("volume")),
            }
        )
    return out


def _argmax_close(indices: Sequence[int], series: List[Dict[str, Any]]) -> Optional[int]:
    """在给定索引集合中找 close 最大的索引；相同最大值取更早的那个。"""
    best_i = None
    best_v = None
    for i in indices:
        if i < 0 or i >= len(series):
            continue
        v = _safe_float(series[i].get("close"))
        if best_v is None or v > best_v or (v == best_v and (best_i is None or i < best_i)):
            best_v = v
            best_i = i
    return best_i


def _argmin_close(indices: Sequence[int], series: List[Dict[str, Any]]) -> Optional[int]:
    """在给定索引集合中找 close 最小的索引；相同最小值取更早的那个。"""
    best_i = None
    best_v = None
    for i in indices:
        if i < 0 or i >= len(series):
            continue
        v = _safe_float(series[i].get("close"))
        if best_v is None or v < best_v or (v == best_v and (best_i is None or i < best_i)):
            best_v = v
            best_i = i
    return best_i


def _argmax_high(indices: Sequence[int], series: List[Dict[str, Any]]) -> Optional[int]:
    """在给定索引集合中找 high 最大的索引；相同最大值取更早的那个。"""
    best_i = None
    best_v = None
    for i in indices:
        if i < 0 or i >= len(series):
            continue
        v = _safe_float(series[i].get("high"))
        if best_v is None or v > best_v or (v == best_v and (best_i is None or i < best_i)):
            best_v = v
            best_i = i
    return best_i


def find_m_top_signals(series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对单只股票的日线序列扫描 M头。
    返回信号列表，每条信号包含触发日(today) + X/Y/Z。
    """
    signals: List[Dict[str, Any]] = []
    n = len(series)
    if n < 15:
        return signals

    for t in range(0, n):
        # Step1 需要窗口 t-4..t
        if t < 4:
            continue
        window_idx = list(range(t - 4, t + 1))
        closes = [_safe_float(series[i].get("close")) for i in window_idx]
        if not closes:
            continue
        max_close = max(closes)

        close_today = _safe_float(series[t].get("close"))
        close_yesterday = _safe_float(series[t - 1].get("close"))
        # 今天/昨日不能是窗口最大收盘
        if close_today >= max_close or close_yesterday >= max_close:
            continue

        x = _argmax_close(window_idx, series)
        if x is None:
            continue
        if x in (t, t - 1):
            # 理论上前面已经过滤，但再保护一次
            continue

        # Step2: 需要 X-3..X-1 存在
        if x < 3:
            continue
        prev3 = [x - 1, x - 2, x - 3]
        x_close = _safe_float(series[x].get("close"))
        x_high = _safe_float(series[x].get("high"))
        ok2 = True
        for i in prev3:
            d_close = _safe_float(series[i].get("close"))
            d_high = _safe_float(series[i].get("high"))
            if not (x_close > d_close and x_high > d_high):
                ok2 = False
                break
            if _pct_up(x_high, d_close) <= 5.0:
                ok2 = False
                break
        if not ok2:
            continue

        # Step3: 从 X 往前至多5日 (X-5..X-1) 找收盘最低 Y
        if x < 1:
            continue
        start3 = max(0, x - 5)
        idx3 = list(range(start3, x))  # 不包含X
        if not idx3:
            continue
        y = _argmin_close(idx3, series)
        if y is None:
            continue
        y_high = _safe_float(series[y].get("high"))
        if y_high <= 0:
            continue
        if not (x_close > y_high and _pct_up(x_close, y_high) > 5.0):
            continue

        # Step4: 从 Y 往前至多5日 (Y-5..Y-1) 找最高价最高 Z
        if y < 1:
            continue
        start4 = max(0, y - 5)
        idx4 = list(range(start4, y))
        if not idx4:
            continue
        z = _argmax_high(idx4, series)
        if z is None:
            continue
        z_close = _safe_float(series[z].get("close"))
        z_high = _safe_float(series[z].get("high"))
        y_close = _safe_float(series[y].get("close"))
        if y_close <= 0:
            continue
        if not (z_close > y_close and _pct_up(z_close, y_close) > 5.0):
            continue

        # Step5: Z.high > X.high
        if not (z_high > x_high):
            continue

        # Step6: Z.volume > X.volume
        x_vol = _safe_float(series[x].get("volume"))
        z_vol = _safe_float(series[z].get("volume"))
        if not (z_vol > x_vol):
            continue

        signals.append(
            {
                "trigger_date": series[t].get("date"),
                "x_date": series[x].get("date"),
                "y_date": series[y].get("date"),
                "z_date": series[z].get("date"),
                "x_close": x_close,
                "x_high": x_high,
                "x_vol": x_vol,
                "y_close": y_close,
                "y_high": y_high,
                "z_close": z_close,
                "z_high": z_high,
                "z_vol": z_vol,
            }
        )

    return signals


def _parse_stock_list(args: argparse.Namespace) -> List[str]:
    out: List[str] = []

    if args.stocks:
        for s in args.stocks:
            if not s:
                continue
            # 允许逗号/空格混输
            parts = [p.strip() for p in str(s).replace("，", ",").split(",")]
            for p in parts:
                if p:
                    out.append(p.upper())

    if args.stocks_file:
        path = args.stocks_file
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = [p.strip() for p in line.replace("，", ",").split(",")]
                    for p in parts:
                        if p:
                            out.append(p.upper())
        except Exception as e:
            print(f"[ERROR] 读取股票列表文件失败: {path} | {e}")

    if not out:
        out = list(DEFAULT_STOCKS)

    # 去重但保持顺序
    seen = set()
    uniq = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def _write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not path:
        return
    headers = [
        "stock_code",
        "trigger_date",
        "x_date",
        "y_date",
        "z_date",
        "x_close",
        "x_high",
        "x_vol",
        "y_close",
        "y_high",
        "z_close",
        "z_high",
        "z_vol",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in headers})


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描M头形态(从MySQL日线数据)")
    parser.add_argument(
        "--stocks",
        nargs="*",
        help="股票代码列表，如: --stocks SZ300188 SH603556 或 --stocks SZ300188,SH603556",
        default=None,
    )
    parser.add_argument("--stocks-file", help="从文件读取股票列表(每行一个或逗号分隔)", default=None)
    parser.add_argument("--start", help="起始日期(YYYY-MM-DD)，默认 2024-01-01", default="2024-01-01")
    parser.add_argument(
        "--end",
        help="结束日期(YYYY-MM-DD)，默认 今天",
        default=None,
    )
    parser.add_argument("--out", help="可选：输出CSV路径", default=None)
    parser.add_argument("--print-all", action="store_true", help="输出每只股票的所有触发日(默认只输出最近一次)", default=False)
    args = parser.parse_args()

    start_date = str(args.start).strip()
    end_date = str(args.end).strip() if args.end else date.today().strftime("%Y-%m-%d")

    # 简单校验日期格式
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except Exception:
        print(f"[ERROR] 日期格式错误: start={start_date}, end={end_date} (需要 YYYY-MM-DD)")
        return

    stocks = _parse_stock_list(args)
    print("=" * 88)
    print("M头形态扫描")
    print(f"时间范围: {start_date} ~ {end_date}")
    print(f"股票数量: {len(stocks)}")
    print("=" * 88)

    all_hits: List[Dict[str, Any]] = []
    ok_cnt = 0
    for code in stocks:
        try:
            series = load_daily_kline_series(code, start_date, end_date)
        except Exception as e:
            print(f"[WARN] {code} 读取日线失败: {e}")
            continue

        if not series:
            print(f"[WARN] {code} 无日线数据(或表不存在/范围内无数据)")
            continue

        hits = find_m_top_signals(series)
        if not hits:
            continue

        ok_cnt += 1
        if args.print_all:
            for h in hits:
                row = {"stock_code": code, **h}
                all_hits.append(row)
                print(
                    f"{code} | 触发日={h['trigger_date']} | X={h['x_date']} | Y={h['y_date']} | Z={h['z_date']}"
                )
        else:
            h = hits[-1]  # 最近一次
            row = {"stock_code": code, **h}
            all_hits.append(row)
            print(
                f"{code} | 最近触发日={h['trigger_date']} | X={h['x_date']} | Y={h['y_date']} | Z={h['z_date']}"
            )

    print("-" * 88)
    print(f"命中股票数: {ok_cnt}")
    print(f"命中记录数: {len(all_hits)}")
    if args.out:
        try:
            _write_csv(args.out, all_hits)
            print(f"已输出CSV: {args.out}")
        except Exception as e:
            print(f"[ERROR] 输出CSV失败: {e}")
    print("=" * 88)


if __name__ == "__main__":
    main()


