"""
从接口批量回填 b_daily_chance（只更新日线赔率得分 day_win_ratio_score）

接口：
    http://121.5.174.81:8005/stock/getDailyChanceWithBeauty

需求调整：
- stock_nature 必须读取数据库 all_stock 表的 nature 字段
- 只更新 day_win_ratio_score，来源 winRatioDescription 中的“日线赔率得分”
- 跳过 2025-09-25 之前的数据，已存在则更新

使用示例：
    # 只跑前5支股票验证
    python fill_daily_chance_from_api.py --limit 5

    # 全量回填 2025-09-25 到今天
    python fill_daily_chance_from_api.py

    # 自定义日期范围 / 指定股票
    python fill_daily_chance_from_api.py --start 2025-10-01 --end 2025-12-10 --codes SZ301565,SH688701
"""

import sys
import os
import argparse
import logging
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

import pymysql
import requests

# 路径（先插入，再导入 domain 服务）
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

from domain.services.bullish_pattern_service import BullishPatternService
from domain.services.bearish_pattern_service import BearishPatternService
from domain.services.volume_type_service import VolumeTypeService

SERVICES_AVAILABLE = True

# ===== 数据库配置（生产主库，用于写入 b_daily_chance） =====
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 接口地址
API_BASE_URL = "http://121.5.174.81:8005"
API_PATH = "/stock/getDailyChanceWithBeauty"

# 默认日期范围：仅跑今天
DEFAULT_START = date.today().strftime("%Y-%m-%d")
DEFAULT_END = date.today().strftime("%Y-%m-%d")

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fill_daily_chance_from_api")


# ========= 工具函数 =========
def load_stocks_from_db(conn, limit: Optional[int], codes: Optional[List[str]], offset: int = 0) -> List[Dict]:
    """
    从 all_stock 读取股票与 nature
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    where_clauses = ["(`is_delist` != 1 OR `is_delist` IS NULL)"]
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
        stocks.append({
            "code": (row.get("code") or "").upper(),
            "name": row.get("name") or "",
            "nature": row.get("nature") or "",
            "table_name": f"basic_data_{(row.get('code') or '').lower()}",
        })

    logger.info(f"📊 加载股票数: {len(stocks)}")
    return stocks


def get_master_connection():
    return pymysql.connect(**MASTER_DB_CONFIG)


def parse_win_ratios(desc: str) -> Tuple[float, float, float]:
    """解析日/周/总赔率得分，缺失则为0"""
    day = week = total = 0.0
    if not desc:
        return day, week, total
    try:
        m = re.search(r"日线赔率得分[：:]\s*([\d.]+)", desc)
        if m:
            day = float(m.group(1))
        m = re.search(r"周线赔率得分[：:]\s*([\d.]+)", desc)
        if m:
            week = float(m.group(1))
        m = re.search(r"赔率总分[：:]\s*([\d.]+)", desc)
        if m:
            total = float(m.group(1))
    except Exception:
        pass
    return day, week, total


def calculate_volume_and_patterns(stock_code: str, table_name: str, date_str: str) -> Tuple[str, str, str]:
    """计算成交量类型、多头、空头组合"""
    if not SERVICES_AVAILABLE:
        return "", "", ""
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        volume_type = VolumeTypeService.calculate_volume_type(table_name, target_date) or ""
        bullish_patterns = BullishPatternService.identify_bullish_patterns(stock_code, table_name, target_date)
        bearish_patterns = BearishPatternService.identify_bearish_patterns(stock_code, table_name, target_date)
        bullish_pattern = ",".join(bullish_patterns) if bullish_patterns else ""
        bearish_pattern = ",".join(bearish_patterns) if bearish_patterns else ""
        return volume_type, bullish_pattern, bearish_pattern
    except Exception:
        return "", "", ""


def fetch_api_data(stock_code: str) -> List[Dict]:
    """调用接口，返回列表数据（可能包含多天）"""
    url = f"{API_BASE_URL}{API_PATH}"
    try:
        resp = requests.post(
            url,
            data=stock_code,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.debug(f"  {stock_code} API status {resp.status_code}")
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.debug(f"  {stock_code} API 请求失败: {e}")
        return []


def upsert_daily_chance(conn, rows: List[Dict]):
    """批量 upsert 到 b_daily_chance（更新日/周/总赔率 + 支撑/压力 + 量型/多头/空头）"""
    if not rows:
        return 0
    cursor = conn.cursor()
    sql = """
        INSERT INTO b_daily_chance
        (stock_code, stock_name, stock_nature, date,
         day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
         support_price, pressure_price, volume_type, bullish_pattern, bearish_pattern, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            stock_nature = VALUES(stock_nature),
            day_win_ratio_score = VALUES(day_win_ratio_score),
            week_win_ratio_score = VALUES(week_win_ratio_score),
            total_win_ratio_score = VALUES(total_win_ratio_score),
            support_price = VALUES(support_price),
            pressure_price = VALUES(pressure_price),
            volume_type = VALUES(volume_type),
            bullish_pattern = VALUES(bullish_pattern),
            bearish_pattern = VALUES(bearish_pattern),
            updated_at = NOW()
    """
    params = []
    for r in rows:
        params.append((
            r["stock_code"],
            r["stock_name"],
            r["stock_nature"],
            r["date"],
            r["day_win_ratio_score"],
            r["week_win_ratio_score"],
            r["total_win_ratio_score"],
            r["support_price"],
            r["pressure_price"],
            r["volume_type"],
            r["bullish_pattern"],
            r["bearish_pattern"],
        ))
    cursor.executemany(sql, params)
    conn.commit()
    return len(rows)


def process_stock(conn, stock: Dict, start_date: date, end_date: date) -> int:
    """处理单只股票，返回写入条数"""
    code = stock["code"]
    name = stock["name"]
    nature = stock["nature"]
    table_name = stock.get("table_name") or f"basic_data_{code.lower()}"

    data_list = fetch_api_data(code)
    if not data_list:
        logger.info(f"  ⚠️ {code} 无数据")
        return 0

    rows = []
    for item in data_list:
        day_str = (item.get("day") or "").split(" ")[0]
        if not day_str:
            continue
        try:
            day_dt = datetime.strptime(day_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if day_dt < start_date or day_dt > end_date:
            continue

        desc = item.get("winRatioDescription", "")
        day_score, week_score, total_score = parse_win_ratios(desc)

        support_price = item.get("supportPrice")
        pressure_price = item.get("pressurePrice")
        try:
            support_price = float(support_price) if support_price not in (None, "") else None
        except Exception:
            support_price = None
        try:
            pressure_price = float(pressure_price) if pressure_price not in (None, "") else None
        except Exception:
            pressure_price = None

        volume_type, bullish_pattern, bearish_pattern = calculate_volume_and_patterns(
            code, table_name, day_str
        )

        rows.append({
            "stock_code": code,
            "stock_name": name,
            "stock_nature": nature,
            "date": day_str,
            "day_win_ratio_score": day_score,
            "week_win_ratio_score": week_score,
            "total_win_ratio_score": total_score,
            "support_price": support_price,
            "pressure_price": pressure_price,
            "volume_type": volume_type,
            "bullish_pattern": bullish_pattern,
            "bearish_pattern": bearish_pattern,
        })

    if not rows:
        logger.info(f"  ℹ️ {code} 无需更新（日期不在范围或无有效记录）")
        return 0

    inserted = upsert_daily_chance(conn, rows)
    logger.info(f"  ✅ {code} {name} 写入/更新 {inserted} 条")
    return inserted


# ========= 主流程 =========
def run_once(start_dt: date, end_dt: date, limit: int, offset: int, codes: Optional[List[str]]):
    """执行一次回填"""
    try:
        conn = get_master_connection()
        logger.info(f"✅ 已连接主库 {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
    except Exception as e:
        logger.error(f"❌ 连接主库失败: {e}")
        return

    stocks = load_stocks_from_db(conn, limit=limit, codes=codes, offset=offset)
    if not stocks:
        logger.error("❌ 未加载到任何股票")
        conn.close()
        return

    total_rows = 0
    try:
        for i, stock in enumerate(stocks, 1):
            logger.info(f"[{i}/{len(stocks)}] 处理 {stock['code']} ({stock['name']}) ...")
            total_rows += process_stock(conn, stock, start_dt, end_dt)
    finally:
        conn.close()
        logger.info("✅ 已关闭数据库连接")

    logger.info("📊 完成")
    logger.info(f"总写入/更新: {total_rows} 条")


def main():
    parser = argparse.ArgumentParser(description="批量回填 b_daily_chance（赔率+支撑/压力+量型/多空）")
    parser.add_argument("--start", type=str, default=DEFAULT_START, help="开始日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--end", type=str, default=DEFAULT_END, help=f"结束日期 YYYY-MM-DD，默认今天 {DEFAULT_END}")
    parser.add_argument("--today", action="store_true", help="仅跑今天（start=end=今天，默认行为）")
    parser.add_argument("--limit", type=int, default=0, help="限制股票数量（测试用）")
    parser.add_argument("--offset", type=int, default=0, help="从第 offset 条开始（用于断点续跑）")
    parser.add_argument("--codes", type=str, help="指定股票代码，逗号分隔，如 SZ301565,SH688701")
    parser.add_argument("--scheduler", action="store_true", help="启动定时任务（每日17:15跑当日数据）")
    args = parser.parse_args()

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").date()
    except Exception:
        logger.error("❌ 日期格式错误，应为 YYYY-MM-DD")
        sys.exit(1)

    if args.today:
        start_dt = end_dt = date.today()

    codes = None
    if args.codes:
        codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()]

    if args.scheduler:
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.error("❌ APScheduler 未安装，请运行: pip install APScheduler")
            sys.exit(1)

        scheduler = BlockingScheduler()

        def job():
            today = date.today()
            logger.info("🌟 定时任务：跑当日数据")
            run_once(today, today, limit=args.limit, offset=args.offset, codes=codes)

        scheduler.add_job(job, CronTrigger(hour=17, minute=40), id="fill_daily_chance", replace_existing=True)
        logger.info("✅ 定时任务已启动：每日 17:15 跑当日数据")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("⛔ 定时任务已停止")
    else:
        run_once(start_dt, end_dt, limit=args.limit, offset=args.offset, codes=codes)


if __name__ == "__main__":
    main()

