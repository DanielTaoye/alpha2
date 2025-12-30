"""
刷新 b_daily_chance 表的成交量类型和多空头组合

功能：
- 从 stock_list.csv 读取股票列表
- 刷新每个股票每天的成交量类型（volume_type）
- 刷新每个股票每天的多头组合（bullish_pattern）
- 刷新每个股票每天的空头组合（bearish_pattern）

使用方式：
- 测试5个股票: python refresh_volume_and_patterns.py --test
- 刷新全部股票: python refresh_volume_and_patterns.py --all
- 指定股票代码: python refresh_volume_and_patterns.py --codes SZ301565,SH688701
"""

import sys
import os
import csv
import json
import argparse
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Set, Tuple
import logging
import time

# 添加路径
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

import pymysql
import pymysql.cursors
import requests
import re

# ============ 数据库配置 ============
# 生产主库（用于更新 b_daily_chance 表）
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 只读库（用于获取 K线数据）
READONLY_DB_CONFIG = {
    'host': 'sh-cdbrg-8f14w39q.sql.tencentcdb.com',
    'port': 25924,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 股票列表文件
STOCK_LIST_FILE = os.path.join(project_root, 'stock_list.csv')
STOCK_CONFIG_FILE = os.path.join(backend_dir, 'infrastructure', 'config', 'stock_config.json')

# 每日机会接口
API_BASE_URL = "http://121.5.174.81:8005"
API_PATH = "/stock/getDailyChanceWithBeauty"

# 默认需要检查/补齐的历史范围
DEFAULT_HISTORY_START = "2024-01-01"

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 尝试导入 KLinePatternService
try:
    from domain.services.kline_pattern_service import KLinePatternService
    KLINE_SERVICE_AVAILABLE = True
    logger.info("✅ KLinePatternService 导入成功")
except Exception as e:
    logger.warning(f"⚠️ 无法导入 KLinePatternService: {e}")
    KLINE_SERVICE_AVAILABLE = False


def parse_win_ratios(desc: str) -> Tuple[float, float, float]:
    """解析日/周/总赔率得分，缺失则为0"""
    day_score = week_score = total_score = 0.0
    if not desc:
        return day_score, week_score, total_score
    try:
        m = re.search(r"日线赔率得分[：:]\s*([\d.]+)", desc)
        if m:
            day_score = float(m.group(1))
        m = re.search(r"周线赔率得分[：:]\s*([\d.]+)", desc)
        if m:
            week_score = float(m.group(1))
        m = re.search(r"赔率总分[：:]\s*([\d.]+)", desc)
        if m:
            total_score = float(m.group(1))
    except Exception:
        pass
    return day_score, week_score, total_score


def fetch_daily_chance_from_api(stock_code: str, timeout: int = 30) -> List[Dict]:
    """
    调用 getDailyChanceWithBeauty 接口，返回 list[dict]（通常包含多天）
    注意：接口要求 POST，body 直接传股票代码字符串。
    """
    url = f"{API_BASE_URL}{API_PATH}"
    try:
        resp = requests.post(
            url,
            data=stock_code,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(f"每日机会API请求失败: 股票={stock_code}, status={resp.status_code}")
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except requests.Timeout:
        logger.warning(f"每日机会API超时: 股票={stock_code}")
        return []
    except Exception as e:
        logger.warning(f"每日机会API异常: 股票={stock_code}, 错误={e}")
        return []


def get_stock_nature_from_all_stock(conn, stock_code: str) -> str:
    """从 all_stock 表尝试补齐 nature（股性）。找不到则返回空字符串。"""
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT nature FROM all_stock WHERE code = %s LIMIT 1", (stock_code,))
        row = cursor.fetchone()
        return (row.get("nature") or "") if row else ""
    except Exception:
        return ""


def get_trading_dates_from_basic_data(conn, table_name: str, start_date: str, end_date: str) -> List[str]:
    """
    从日K表抽取交易日清单（以只读库为准）。
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = f"""
        SELECT DISTINCT DATE(shi_jian) AS d
        FROM {table_name}
        WHERE peroid_type = '1day'
          AND DATE(shi_jian) >= %s
          AND DATE(shi_jian) <= %s
        ORDER BY d ASC
    """
    cursor.execute(sql, (start_date, end_date))
    rows = cursor.fetchall()
    dates: List[str] = []
    for r in rows:
        d = r.get("d")
        if not d:
            continue
        if isinstance(d, datetime):
            dates.append(d.strftime("%Y-%m-%d"))
        elif isinstance(d, date):
            dates.append(d.strftime("%Y-%m-%d"))
        else:
            dates.append(str(d))
    return dates


def get_existing_dates_in_b_daily_chance(conn, stock_code: str, start_date: str, end_date: str) -> Set[str]:
    """查询 b_daily_chance 在区间内已存在的日期集合。"""
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT DISTINCT DATE(date) AS d
        FROM b_daily_chance
        WHERE stock_code = %s
          AND DATE(date) >= %s
          AND DATE(date) <= %s
    """
    cursor.execute(sql, (stock_code, start_date, end_date))
    rows = cursor.fetchall()
    s: Set[str] = set()
    for r in rows:
        d = r.get("d")
        if not d:
            continue
        if isinstance(d, datetime):
            s.add(d.strftime("%Y-%m-%d"))
        elif isinstance(d, date):
            s.add(d.strftime("%Y-%m-%d"))
        else:
            s.add(str(d))
    return s


def insert_placeholders_if_missing(
    conn,
    stock_code: str,
    stock_name: str,
    stock_nature: str,
    missing_dates: List[str],
    batch_size: int = 500,
) -> int:
    """
    为缺失日期插入占位记录（仅插入缺失，不覆盖已有）。
    注意：占位记录会把赔率/支撑/压力/量型/形态置为默认值（0/NULL/空串）。
    """
    if not missing_dates:
        return 0
    cursor = conn.cursor()
    sql = """
        INSERT IGNORE INTO b_daily_chance
        (stock_code, stock_name, stock_nature, date,
         day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
         support_price, pressure_price, volume_type, bullish_pattern, bearish_pattern, updated_at)
        VALUES (%s, %s, %s, %s, 0, 0, 0, NULL, NULL, '', '', '', NOW())
    """
    inserted = 0
    params: List[Tuple] = []
    for d in missing_dates:
        params.append((stock_code, stock_name, stock_nature, d))
        if len(params) >= batch_size:
            cursor.executemany(sql, params)
            conn.commit()
            inserted += cursor.rowcount
            params = []
    if params:
        cursor.executemany(sql, params)
        conn.commit()
        inserted += cursor.rowcount
    return inserted


def upsert_scores_support_pressure_from_api(
    conn,
    stock_code: str,
    stock_name: str,
    stock_nature: str,
    start_date: str,
    end_date: str,
) -> int:
    """
    从接口拉取数据并 upsert 到 b_daily_chance：
    - 插入缺失行
    - 若已存在则更新“赔率/支撑/压力/名称/股性”
    - 不覆盖 volume_type / bullish_pattern / bearish_pattern（避免把你后续刷出来的结果清空）
    """
    data_list = fetch_daily_chance_from_api(stock_code)
    if not data_list:
        return 0

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    rows: List[Tuple] = []
    for item in data_list:
        day_str = (item.get("day") or "").split(" ")[0]
        if not day_str:
            continue
        try:
            d = datetime.strptime(day_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < start_dt or d > end_dt:
            continue

        desc = item.get("winRatioDescription", "") or ""
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

        rows.append((
            stock_code, stock_name, stock_nature, day_str,
            day_score, week_score, total_score,
            support_price, pressure_price
        ))

    if not rows:
        return 0

    cursor = conn.cursor()
    sql = """
        INSERT INTO b_daily_chance
        (stock_code, stock_name, stock_nature, date,
         day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
         support_price, pressure_price, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            stock_nature = VALUES(stock_nature),
            day_win_ratio_score = VALUES(day_win_ratio_score),
            week_win_ratio_score = VALUES(week_win_ratio_score),
            total_win_ratio_score = VALUES(total_win_ratio_score),
            support_price = VALUES(support_price),
            pressure_price = VALUES(pressure_price),
            updated_at = NOW()
    """
    cursor.executemany(sql, rows)
    conn.commit()
    return len(rows)


def load_stock_list_from_csv() -> List[Dict]:
    """从 stock_list.csv 读取股票列表"""
    stocks = []
    
    logger.info(f"📁 股票列表文件路径: {STOCK_LIST_FILE}")
    logger.info(f"📁 文件是否存在: {os.path.exists(STOCK_LIST_FILE)}")
    
    if not os.path.exists(STOCK_LIST_FILE):
        logger.error(f"❌ 股票列表文件不存在: {STOCK_LIST_FILE}")
        return stocks
    
    try:
        with open(STOCK_LIST_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('code', '').strip()
                name = row.get('name', '').strip()
                if code:
                    stocks.append({
                        'code': code,
                        'name': name,
                        'table_name': f"basic_data_{code.lower()}"
                    })
    except Exception as e:
        logger.error(f"❌ 读取CSV文件失败: {e}")
    
    logger.info(f"📊 从 CSV 加载了 {len(stocks)} 支股票")
    return stocks


def load_stock_list_from_json() -> List[Dict]:
    """从 stock_config.json 读取股票列表（包含所有分类的股票）"""
    stocks = []
    
    logger.info(f"📁 股票配置文件路径: {STOCK_CONFIG_FILE}")
    logger.info(f"📁 文件是否存在: {os.path.exists(STOCK_CONFIG_FILE)}")
    
    if not os.path.exists(STOCK_CONFIG_FILE):
        logger.error(f"❌ 股票配置文件不存在: {STOCK_CONFIG_FILE}")
        return stocks
    
    try:
        with open(STOCK_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
            # 遍历所有分类（波段、短线、中长线）
            for category, stock_list in config.items():
                if isinstance(stock_list, list):
                    for stock in stock_list:
                        code = stock.get('code', '').strip()
                        name = stock.get('name', '').strip()
                        table = stock.get('table', '').strip()
                        
                        if code:
                            stocks.append({
                                'code': code,
                                'name': name,
                                'table_name': table if table else f"basic_data_{code.lower()}",
                                'category': category
                            })
    except Exception as e:
        logger.error(f"❌ 读取JSON文件失败: {e}")
    
    logger.info(f"📊 从 JSON 配置加载了 {len(stocks)} 支股票")
    return stocks


def get_master_connection():
    """获取生产主库连接（用于更新）"""
    return pymysql.connect(**MASTER_DB_CONFIG)


def get_readonly_connection():
    """获取只读库连接（用于读取K线数据）"""
    return pymysql.connect(**READONLY_DB_CONFIG)


def get_all_dates_for_stock(conn, stock_code: str) -> List[str]:
    """获取 b_daily_chance 表中该股票的所有日期"""
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    sql = """
        SELECT DISTINCT DATE(date) as date
        FROM b_daily_chance
        WHERE stock_code = %s
        ORDER BY date ASC
    """
    
    cursor.execute(sql, (stock_code,))
    results = cursor.fetchall()
    
    dates = []
    for row in results:
        if row['date']:
            date_val = row['date']
            if isinstance(date_val, datetime):
                dates.append(date_val.strftime('%Y-%m-%d'))
            elif isinstance(date_val, str):
                dates.append(date_val)
            else:
                dates.append(str(date_val))
    
    return dates


def get_daily_data_batch(conn, table_name: str, start_date: str, end_date: str) -> List[Dict]:
    """批量获取日线数据"""
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        query = f"""
            SELECT shi_jian as date, kai_pan_jia as open, shou_pan_jia as close,
                   zui_gao_jia as high, zui_di_jia as low, cheng_jiao_liang as volume
            FROM {table_name}
            WHERE peroid_type = '1day' 
              AND DATE(shi_jian) >= %s 
              AND DATE(shi_jian) <= %s
            ORDER BY shi_jian ASC
        """
        
        cursor.execute(query, (start_date, end_date))
        results = cursor.fetchall()
        
        daily_list = []
        for i, row in enumerate(results):
            date_value = row['date']
            if isinstance(date_value, datetime):
                date_obj = date_value
            else:
                try:
                    if isinstance(date_value, str):
                        date_obj = datetime.strptime(date_value.split()[0], '%Y-%m-%d')
                    else:
                        date_obj = datetime.combine(date_value, datetime.min.time())
                except:
                    date_obj = date_value
            
            daily_item = {
                'date': date_obj,
                'open': float(row['open']) if row['open'] else 0,
                'close': float(row['close']) if row['close'] else 0,
                'high': float(row['high']) if row['high'] else 0,
                'low': float(row['low']) if row['low'] else 0,
                'volume': int(row['volume']) / 100 if row['volume'] else 0  # 数据库存储需要除以100
            }
            # 添加前一日收盘价
            if i > 0:
                daily_item['prev_close'] = float(results[i-1]['close']) if results[i-1]['close'] else 0
            daily_list.append(daily_item)
        
        return daily_list
        
    except Exception as e:
        logger.debug(f"获取日线数据失败: {table_name}: {e}")
        return []


# ============ 成交量类型计算逻辑 (复用现有逻辑) ============

def check_abc_volume_type(daily_data: List[Dict], idx: int) -> Optional[str]:
    """检查指定索引位置的成交量是否为A/B/C类型"""
    if idx < 1:
        return None
    
    target_volume = daily_data[idx]['volume']
    
    # 检查类型A
    if idx >= 1:
        prev_volume = daily_data[idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if 2.0 <= ratio <= 3.0:
                return 'A'
    
    # 检查类型B
    if idx >= 3:
        prev_3_volumes = [daily_data[i]['volume'] for i in range(idx - 3, idx)]
        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                return 'B'
    
    # 检查类型C
    if idx >= 5:
        prev_5_volumes = [daily_data[i]['volume'] for i in range(idx - 5, idx)]
        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                return 'C'
    
    return None


def check_all_volume_types(daily_data: List[Dict], idx: int) -> Optional[str]:
    """检查指定索引位置的成交量是否为A/B/C/D/S类型（含S）"""
    if idx < 1:
        return None
    
    target_volume = daily_data[idx]['volume']
    matched_types = []
    
    # 先判 S（相对前一日1.2倍及以上）
    if idx >= 1:
        prev_volume = daily_data[idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if ratio >= 1.2:
                matched_types.append('S')
    
    # 检查类型A
    if idx >= 1:
        prev_volume = daily_data[idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if 2.0 <= ratio <= 3.0:
                matched_types.append('A')
    
    # 检查类型B
    if idx >= 3:
        prev_3_volumes = [daily_data[i]['volume'] for i in range(idx - 3, idx)]
        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                matched_types.append('B')
    
    # 检查类型C
    if idx >= 5:
        prev_5_volumes = [daily_data[i]['volume'] for i in range(idx - 5, idx)]
        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                matched_types.append('C')
    
    # 检查类型D
    if idx >= 5:
        x_day_volume = None
        for i in range(max(0, idx - 5), idx):
            check_volume_type = check_abc_volume_type(daily_data, i)
            if check_volume_type in ['A', 'B', 'C']:
                x_day_volume = daily_data[i]['volume']
                break
        
        if x_day_volume and x_day_volume > 0:
            ratio = target_volume / x_day_volume
            if ratio >= 1.2:
                matched_types.append('D')
    
    if matched_types:
        # 去重保持原顺序
        deduped = []
        for t in matched_types:
            if t not in deduped:
                deduped.append(t)
        return ','.join(deduped)
    return None


def calculate_volume_type_for_idx(daily_data: List[Dict], target_idx: int) -> Optional[str]:
    """计算指定索引位置的成交量类型（含S）"""
    if target_idx < 1:
        return None
    
    target_volume = daily_data[target_idx]['volume']
    matched_types = []
    
    # 先判 S（相对前一日1.2倍及以上）
    if target_idx >= 1:
        prev_volume = daily_data[target_idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if ratio >= 1.2:
                matched_types.append('S')
    
    # 计算类型A: 当日为前1日成交均量的2倍-3倍
    if target_idx >= 1:
        prev_volume = daily_data[target_idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if 2.0 <= ratio <= 3.0:
                matched_types.append('A')
    
    # 计算类型B: 当日为前3日成交均量的2倍及以上
    if target_idx >= 3:
        prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                matched_types.append('B')
    
    # 计算类型C: 当日为前5日成交均量的2倍及以上
    if target_idx >= 5:
        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                matched_types.append('C')
    
    # 计算类型D: 前五日出现过ABC任意一种放量，今日的成交量为X日的1.2倍以上
    if target_idx >= 5:
        x_day_volume = None
        for i in range(max(0, target_idx - 5), target_idx):
            check_volume_type = check_abc_volume_type(daily_data, i)
            if check_volume_type in ['A', 'B', 'C']:
                x_day_volume = daily_data[i]['volume']
                break
        
        if x_day_volume and x_day_volume > 0:
            ratio = target_volume / x_day_volume
            if ratio >= 1.2:
                matched_types.append('D')
    
    # 计算类型E: 当日为前1日以及前五日均值的4倍以上（前五日未出现ABCD任何一种放量）
    if target_idx >= 5:
        has_abcd_in_prev_5 = False
        for i in range(max(0, target_idx - 5), target_idx):
            check_types = check_all_volume_types(daily_data, i)
            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                has_abcd_in_prev_5 = True
                break
        
        if not has_abcd_in_prev_5:
            prev_volume = daily_data[target_idx - 1]['volume'] if target_idx >= 1 else 0
            prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
            avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
            
            if prev_volume > 0 and avg_5_volume > 0:
                ratio_to_prev = target_volume / prev_volume
                ratio_to_avg5 = target_volume / avg_5_volume
                if ratio_to_prev >= 4.0 and ratio_to_avg5 >= 4.0:
                    matched_types.append('E')
    
    # 计算类型F
    if target_idx >= 5:
        x_day_volume = None
        for i in range(max(0, target_idx - 5), target_idx):
            check_types = check_all_volume_types(daily_data, i)
            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                x_day_volume = daily_data[i]['volume']
                break
        
        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
        avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        
        condition1 = False
        if x_day_volume and x_day_volume > 0:
            ratio = target_volume / x_day_volume
            if ratio >= 3.0:
                condition1 = True
        
        condition2 = False
        if avg_5_volume > 0:
            ratio = target_volume / avg_5_volume
            if ratio >= 3.0:
                condition2 = True
        
        if condition1 or condition2:
            matched_types.append('F')
    
    # 计算类型G
    if target_idx >= 5:
        for i in range(max(0, target_idx - 5), target_idx):
            check_types = check_all_volume_types(daily_data, i)
            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                x_day_volume = daily_data[i]['volume']
                if x_day_volume > 0:
                    ratio = target_volume / x_day_volume
                    if ratio >= 0.7:
                        matched_types.append('G')
                        break
    
    # 计算类型H
    if target_idx >= 5:
        for i in range(max(0, target_idx - 5), target_idx):
            check_types = check_all_volume_types(daily_data, i)
            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                x_day_volume = daily_data[i]['volume']
                if target_volume > x_day_volume:
                    matched_types.append('H')
                    break
    
    # 计算类型X: 当日为前3日成交均量的1.5倍及以上
    if target_idx >= 3:
        prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 1.5:
                matched_types.append('X')
    
    # 计算类型Y: 当日为前5日成交均量的1.5倍及以上
    if target_idx >= 5:
        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 1.5:
                matched_types.append('Y')
    
    # 计算类型Z
    if target_idx >= 10:
        has_abc_in_prev_10 = False
        for i in range(max(0, target_idx - 10), target_idx):
            check_types = check_abc_volume_type(daily_data, i)
            if check_types in ['A', 'B', 'C']:
                has_abc_in_prev_10 = True
                break
        
        if has_abc_in_prev_10 and target_idx >= 4:
            yesterday_volume = daily_data[target_idx - 1]['volume']
            prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 4, target_idx - 1)]
            avg_3_volume = sum(prev_3_volumes) / len(prev_3_volumes)
            
            condition1 = False
            if avg_3_volume > 0:
                ratio = yesterday_volume / avg_3_volume
                if ratio >= 1.3:
                    condition1 = True
            
            condition2 = False
            if yesterday_volume > 0:
                ratio = target_volume / yesterday_volume
                if ratio >= 1.08:
                    condition2 = True
            
            if condition1 and condition2:
                matched_types.append('Z')
    
    # 返回所有匹配的类型
    if matched_types:
        seen = set()
        unique_types = []
        # 保持固定顺序，S 放最后
        for t in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z', 'S']:
            if t in matched_types and t not in seen:
                unique_types.append(t)
                seen.add(t)
        return ','.join(unique_types)
    
    return None


# ============ 多头组合计算逻辑 (复用现有逻辑) ============

def calculate_amplitude(high: float, low: float, prev_close: float) -> float:
    """计算振幅"""
    if prev_close == 0:
        return 0.0
    return ((high - low) / prev_close) * 100


def identify_bullish_patterns(stock_code: str, daily_data: List[Dict], target_idx: int, 
                               volume_type_cache: Dict[int, str]) -> List[str]:
    """识别多头组合"""
    if not KLINE_SERVICE_AVAILABLE:
        return []
    
    if target_idx < 1:
        return []
    
    matched_patterns = []
    today = daily_data[target_idx]
    prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None
    
    if not prev_day:
        return []
    
    # 1. 十字星+中阳线
    prev_amplitude = calculate_amplitude(
        prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
    )
    prev_pattern = KLinePatternService.identify_pattern(
        stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
    )
    today_amplitude = calculate_amplitude(
        today['high'], today['low'], prev_day['close']
    )
    today_pattern = KLinePatternService.identify_pattern(
        stock_code, today['open'], today['close'], today['high'], today['low']
    )
    
    if (prev_pattern == "十字星" and prev_amplitude >= 5.0 and
        today_pattern in ["中阳线", "大阳线"] and today_amplitude >= 5.0):
        matched_patterns.append("十字星+中阳线")
    
    # 2. 触底反弹阳线+阳线
    is_positive = today['close'] > today['open']
    if (prev_pattern in ["触底反弹十字星", "触底反弹阳线"] and prev_amplitude >= 5.0 and
        is_positive and today_amplitude >= 6.0):
        matched_patterns.append("触底反弹阳线+阳线")
    
    # 3. 触底反弹阴线+中阳
    if (prev_pattern == "触底反弹阴线" and prev_amplitude >= 5.0 and
        today_pattern in ["中阳线", "大阳线"] and today_amplitude >= 6.0):
        matched_patterns.append("触底反弹阴线+中阳")
    
    # 4. 阳包阴
    prev_abc = KLinePatternService.calculate_abc(
        prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
    )
    prev_prev_close = prev_day.get('prev_close', prev_day['close'])
    prev_change = (prev_day['close'] - prev_prev_close) / prev_prev_close if prev_prev_close > 0 else 0
    prev_change_pct = abs(prev_change) * 100
    is_prev_negative = prev_day['close'] < prev_day['open']
    prev_b_ratio = (prev_abc.b / prev_day['low']) * 100 if prev_day['low'] > 0 else 0
    is_today_positive = today['close'] > today['open']
    is_engulfing = today['close'] >= prev_day['high']
    
    if (is_prev_negative and prev_change_pct > 5.0 and prev_b_ratio >= 4.0 and
        is_today_positive and is_engulfing):
        matched_patterns.append("阳包阴")
    
    # 5. 刺透
    mid_price = (prev_day['open'] + prev_day['close']) / 2
    is_piercing = today['close'] > mid_price
    if (is_prev_negative and prev_change_pct > 5.0 and prev_b_ratio >= 4.0 and
        is_today_positive and is_piercing):
        matched_patterns.append("刺透")
    
    # 6. 双针探底
    if target_idx >= 2:
        prev_patterns = []
        prev_lows = []
        for i in range(max(0, target_idx - 2), target_idx):
            day = daily_data[i]
            amplitude = calculate_amplitude(
                day['high'], day['low'], daily_data[i-1]['close'] if i > 0 else day['close']
            )
            pattern = KLinePatternService.identify_pattern(
                stock_code, day['open'], day['close'], day['high'], day['low']
            )
            if amplitude > 6.0 and pattern in ["触底反弹阳线", "触底反弹阴线", "十字星"]:
                prev_patterns.append(pattern)
                prev_lows.append(day['low'])
        
        if prev_patterns and today_amplitude > 6.0 and today_pattern in ["触底反弹阳线", "触底反弹阴线", "十字星"]:
            today_low = today['low']
            for prev_low in prev_lows:
                if prev_low > 0:
                    price_diff_pct = abs(today_low - prev_low) / prev_low * 100
                    if price_diff_pct < 1.5:
                        matched_patterns.append("双针探底")
                        break
    
    # 7. 一阳穿三阴
    if target_idx >= 3:
        start_idx = max(0, target_idx - 3)
        consecutive_negative_days = 0
        volumes = []
        max_high = 0.0
        earliest_negative_idx = None
        latest_negative_idx = None
        
        for i in range(target_idx - 1, start_idx - 1, -1):
            if i < 0:
                break
            day = daily_data[i]
            is_negative = day['close'] < day['open']
            
            if is_negative:
                if latest_negative_idx is None:
                    latest_negative_idx = i
                earliest_negative_idx = i
                consecutive_negative_days += 1
                max_high = max(max_high, day['high'])
                volumes.insert(0, day.get('volume', 0))
            else:
                if consecutive_negative_days > 0:
                    break
        
        if consecutive_negative_days >= 2 and earliest_negative_idx is not None and earliest_negative_idx > 0:
            start_prev_close = daily_data[earliest_negative_idx - 1]['close']
            end_close = daily_data[latest_negative_idx]['close']
            if start_prev_close > 0:
                total_decline = abs((end_close - start_prev_close) / start_prev_close) * 100
                
                if total_decline > 6.0:
                    is_volume_decreasing = True
                    for i in range(1, len(volumes)):
                        if volumes[i] >= volumes[i-1]:
                            is_volume_decreasing = False
                            break
                    
                    if is_volume_decreasing and is_today_positive:
                        # 使用缓存的成交量类型
                        today_volume_type = volume_type_cache.get(target_idx, '')
                        has_xy = today_volume_type and ('X' in today_volume_type or 'Y' in today_volume_type)
                        
                        if has_xy and today['close'] > max_high:
                            matched_patterns.append("一阳穿三阴")
    
    return matched_patterns


# ============ 空头组合计算逻辑 (复用现有逻辑) ============

def identify_bearish_patterns(stock_code: str, daily_data: List[Dict], target_idx: int) -> List[str]:
    """识别空头组合"""
    if not KLINE_SERVICE_AVAILABLE:
        return []
    
    if target_idx < 1:
        return []
    
    matched_patterns = []
    today = daily_data[target_idx]
    prev_day = daily_data[target_idx - 1] if target_idx >= 1 else None
    
    if not prev_day:
        return []
    
    # 1. 十字星+中阴
    prev_pattern = KLinePatternService.identify_pattern(
        stock_code, prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low'],
        prev_day.get('prev_close')
    )
    
    if prev_pattern == "十字星":
        is_main = KLinePatternService.is_main_board(stock_code)
        decline_threshold = 3.0 if is_main else 5.0
        is_today_negative = today['close'] < today['open']
        if is_today_negative:
            decline = (today['close'] - prev_day['close']) / prev_day['close'] if prev_day['close'] > 0 else 0
            decline_pct = abs(decline) * 100
            if decline_pct >= decline_threshold:
                matched_patterns.append("十字星+中阴")
    
    # 2. 冲高回落阴线+阴线
    prev_amplitude = calculate_amplitude(
        prev_day['high'], prev_day['low'], prev_day.get('prev_close', prev_day['close'])
    )
    if prev_pattern == "冲高回落阴线" and prev_amplitude > 5.0:
        is_today_negative = today['close'] < today['open']
        if is_today_negative:
            decline = (today['close'] - prev_day['close']) / prev_day['close'] if prev_day['close'] > 0 else 0
            decline_pct = abs(decline) * 100
            if decline_pct > 3.0:
                matched_patterns.append("冲高回落阴线+阴线")
    
    # 3. 带上影线的阴线/阳线+阴线
    valid_patterns = ["冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", "冲高回落阴十字星"]
    if prev_pattern in valid_patterns and prev_amplitude > 5.0:
        is_today_negative = today['close'] < today['open']
        if is_today_negative:
            decline = (today['close'] - prev_day['close']) / prev_day['close'] if prev_day['close'] > 0 else 0
            decline_pct = abs(decline) * 100
            if decline_pct > 3.0:
                matched_patterns.append("带上影线的阴线/阳线+阴线")
    
    # 4. 带上影阳线+十字星+（阴线或带上影线阴线）
    if target_idx >= 2:
        day_before_2 = daily_data[target_idx - 2]
        day_before_1 = daily_data[target_idx - 1]
        
        amplitude_2 = calculate_amplitude(
            day_before_2['high'], day_before_2['low'],
            daily_data[target_idx - 3]['close'] if target_idx >= 3 else day_before_2['close']
        )
        pattern_2 = KLinePatternService.identify_pattern(
            stock_code, day_before_2['open'], day_before_2['close'],
            day_before_2['high'], day_before_2['low']
        )
        
        valid_patterns_2 = ["冲高回落阳线", "冲高回落阳十字星"]
        if pattern_2 in valid_patterns_2 and amplitude_2 > 5.0:
            pattern_1 = KLinePatternService.identify_pattern(
                stock_code, day_before_1['open'], day_before_1['close'],
                day_before_1['high'], day_before_1['low']
            )
            if pattern_1 == "十字星":
                today_pattern = KLinePatternService.identify_pattern(
                    stock_code, today['open'], today['close'], today['high'], today['low']
                )
                today_amplitude = calculate_amplitude(
                    today['high'], today['low'], day_before_1['close']
                )
                is_today_negative = today['close'] < today['open']
                decline = (today['close'] - day_before_1['close']) / day_before_1['close'] if day_before_1['close'] > 0 else 0
                decline_pct = abs(decline) * 100
                
                if ((is_today_negative and decline_pct > 3.0) or
                    (today_pattern == "冲高回落阴线" and today_amplitude > 5.0) or
                    (today_pattern == "冲高回落阴十字星" and today_amplitude > 5.0) or
                    (today_pattern == "冲高回落阳线" and today_amplitude > 5.0)):
                    matched_patterns.append("带上影阳线+十字星+（阴线或带上影线阴线）")
    
    # 5. 双针探顶
    if target_idx >= 2:
        prev_highs = []
        for i in range(max(0, target_idx - 2), target_idx):
            day = daily_data[i]
            amplitude = calculate_amplitude(
                day['high'], day['low'],
                daily_data[i-1]['close'] if i > 0 else day['close']
            )
            prev_close_for_pattern = daily_data[i-1]['close'] if i > 0 else day['close']
            pattern = KLinePatternService.identify_pattern(
                stock_code, day['open'], day['close'], day['high'], day['low'], prev_close_for_pattern
            )
            
            if amplitude > 6.0 and pattern in ["冲高回落阳线", "冲高回落阴线", "十字星",
                                               "冲高回落阳十字星", "冲高回落阴十字星",
                                               "高振幅阳十字星", "高振幅阴十字星"]:
                prev_highs.append(day['high'])
        
        if prev_highs:
            today_prev_close = daily_data[target_idx - 1]['close']
            today_amplitude = calculate_amplitude(
                today['high'], today['low'], today_prev_close
            )
            today_pattern = KLinePatternService.identify_pattern(
                stock_code, today['open'], today['close'], today['high'], today['low'], today_prev_close
            )
            
            if today_amplitude > 6.0 and today_pattern in ["冲高回落阳线", "冲高回落阴线", "十字星",
                                                           "冲高回落阳十字星", "冲高回落阴十字星",
                                                           "高振幅阳十字星", "高振幅阴十字星"]:
                today_high = today['high']
                for prev_high in prev_highs:
                    if prev_high > 0:
                        price_diff_pct = abs(today_high - prev_high) / prev_high * 100
                        if price_diff_pct < 1.5:
                            matched_patterns.append("双针探顶")
                            break
    
    # 6. 触底反弹阳线+吞没阴线
    if prev_pattern == "触底反弹阳线" and prev_amplitude > 5.0:
        is_today_negative = today['close'] < today['open']
        if is_today_negative and today['close'] <= prev_day['low']:
            matched_patterns.append("触底反弹阳线+吞没阴线")
    
    # 7. 阴包阳
    prev_abc = KLinePatternService.calculate_abc(
        prev_day['open'], prev_day['close'], prev_day['high'], prev_day['low']
    )
    prev_change = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
    prev_change_pct = prev_change * 100
    is_prev_positive = prev_day['close'] > prev_day['open']
    
    if is_prev_positive:
        is_main = KLinePatternService.is_main_board(stock_code)
        b_threshold = 3.0 if is_main else 5.0
        prev_b_ratio = (prev_abc.b / prev_day['low']) * 100 if prev_day['low'] > 0 else 0
        
        if prev_change_pct > 5.0 and prev_b_ratio > b_threshold:
            is_today_negative = today['close'] < today['open']
            if is_today_negative and today['close'] < prev_day['open']:
                matched_patterns.append("阴包阳")
    
    # 8. T字板/一字板+带上影阴线/高开回落阴线
    if prev_pattern in ["T字型涨停", "一字涨停", "T字型跌停", "一字跌停"]:
        today_amplitude = calculate_amplitude(
            today['high'], today['low'], prev_day['close']
        )
        today_pattern = KLinePatternService.identify_pattern(
            stock_code, today['open'], today['close'], today['high'], today['low']
        )
        
        if today_amplitude > 5.0:
            valid_today_patterns = ["冲高回落阴线", "冲高回落阴十字星"]
            is_today_negative = today['close'] < today['open']
            
            if today_pattern in valid_today_patterns:
                matched_patterns.append("T字板/一字板+带上影阴线/高开回落阴线")
            elif is_today_negative:
                A = today['high'] - today['open']
                B = today['open'] - today['close']
                C = today['close'] - today['low']
                if A > 0 or (C < 2 * B and (A == 0 or A < 3 * B)):
                    matched_patterns.append("T字板/一字板+带上影阴线/高开回落阴线")
    
    # 9. 乌云盖顶
    is_today_negative = today['close'] < today['open']
    if is_today_negative:
        decline = (today['close'] - prev_day['close']) / prev_day['close'] if prev_day['close'] > 0 else 0
        decline_pct = abs(decline) * 100
        
        if decline_pct > 5.0:
            start_idx = max(0, target_idx - 20)
            max_high = 0.0
            for i in range(start_idx, target_idx):
                if i >= 0 and i < len(daily_data):
                    max_high = max(max_high, daily_data[i]['high'])
            
            if max_high > 0 and today['open'] >= max_high:
                matched_patterns.append("乌云盖顶")
    
    # 10. 触底反弹十字星+吞没阴线
    is_rebound_doji = prev_pattern == "触底反弹十字星"
    is_bullish_doji = prev_pattern == "十字星" and prev_day['close'] >= prev_day['open']
    
    if is_rebound_doji or is_bullish_doji:
        is_today_negative = today['close'] < today['open']
        if is_today_negative:
            decline = (today['close'] - prev_day['close']) / prev_day['close'] if prev_day['close'] > 0 else 0
            decline_pct = abs(decline) * 100
            if decline_pct > 5.0:
                matched_patterns.append("触底反弹十字星+吞没阴线")
    
    # 11. 放量冲高回落阴线+次日未反包
    is_prev_negative = prev_day['close'] < prev_day['open']
    if is_prev_negative:
        prev_abc = KLinePatternService.calculate_abc(
            prev_day['open'], prev_day['high'], prev_day['low'], prev_day['close']
        )
        if prev_abc.c > 0:
            if prev_abc.a > 2 * prev_abc.c:
                prev_prev_close = prev_day.get('prev_close', prev_day['open'])
                prev_decline = (prev_day['close'] - prev_prev_close) / prev_prev_close if prev_prev_close > 0 else 0
                prev_decline_pct = abs(prev_decline) * 100
                
                condition1 = prev_amplitude > 5.0 and prev_decline_pct > 4.5
                condition2 = prev_amplitude > 10.0 and prev_decline_pct > 2.0
                
                if (condition1 or condition2) and today['close'] < prev_day['close']:
                    matched_patterns.append("放量冲高回落阴线+次日未反包")
        elif prev_abc.a > 0:
            prev_prev_close = prev_day.get('prev_close', prev_day['open'])
            prev_decline = (prev_day['close'] - prev_prev_close) / prev_prev_close if prev_prev_close > 0 else 0
            prev_decline_pct = abs(prev_decline) * 100
            
            condition1 = prev_amplitude > 5.0 and prev_decline_pct > 4.5
            condition2 = prev_amplitude > 10.0 and prev_decline_pct > 2.0
            
            if (condition1 or condition2) and today['close'] < prev_day['close']:
                matched_patterns.append("放量冲高回落阴线+次日未反包")
    
    # 12. 一阴穿三阳
    if target_idx >= 3:
        is_today_negative = today['close'] < today['open']
        if is_today_negative:
            consecutive_positive_days = 0
            first_positive_idx = None
            
            for i in range(target_idx - 1, max(0, target_idx - 4), -1):
                if i < 0:
                    break
                day = daily_data[i]
                prev_d = daily_data[i - 1] if i > 0 else None
                
                if prev_d and day['close'] > prev_d['close']:
                    first_positive_idx = i
                    consecutive_positive_days += 1
                else:
                    break
            
            if consecutive_positive_days >= 3 and first_positive_idx is not None:
                first_positive_low = daily_data[first_positive_idx]['low']
                if today['close'] < first_positive_low:
                    matched_patterns.append("一阴穿三阳")
    
    # 13. 吞没阴线（二阴或三阴）吞一根阳线
    if target_idx >= 2:
        start_positive_idx = None
        for i in range(target_idx - 1, max(0, target_idx - 4), -1):
            if i < 0:
                break
            day = daily_data[i]
            is_positive = day['close'] > day['open']
            if not is_positive:
                continue
            
            abc = KLinePatternService.calculate_abc(
                day['open'], day['close'], day['high'], day['low']
            )
            b_ratio = (abc.b / day['low']) * 100 if day['low'] > 0 else 0
            change = (day['close'] - day['open']) / day['open'] if day['open'] > 0 else 0
            change_pct = change * 100
            
            if b_ratio > 3.0 and change_pct > 5.0:
                start_positive_idx = i
                break
        
        if start_positive_idx is not None:
            start_positive_open = daily_data[start_positive_idx]['open']
            negative_count = 0
            
            for i in range(start_positive_idx + 1, target_idx + 1):
                if i >= len(daily_data):
                    break
                day = daily_data[i]
                is_negative = day['close'] < day['open']
                
                if is_negative:
                    negative_count += 1
                else:
                    if negative_count > 0:
                        break
            
            if 1 <= negative_count <= 3:
                is_today_negative = today['close'] < today['open']
                if is_today_negative and today['close'] < start_positive_open:
                    matched_patterns.append("吞没阴线（二阴或三阴）吞一根阳线")
    
    # 14. 吞没阴线（1-3根最终吞没一根阳线）
    if target_idx >= 1:
        start_positive_idx = None
        for i in range(target_idx - 1, max(0, target_idx - 4), -1):
            if i < 0:
                break
            day = daily_data[i]
            is_positive = day['close'] > day['open']
            if not is_positive:
                continue
            
            abc = KLinePatternService.calculate_abc(
                day['open'], day['close'], day['high'], day['low']
            )
            b_ratio = (abc.b / day['low']) * 100 if day['low'] > 0 else 0
            change = (day['close'] - day['open']) / day['open'] if day['open'] > 0 else 0
            change_pct = change * 100
            
            if b_ratio > 3.0 and change_pct > 5.0:
                start_positive_idx = i
                break
        
        if start_positive_idx is not None:
            start_positive_open = daily_data[start_positive_idx]['open']
            days_since_positive = target_idx - start_positive_idx
            
            if 1 <= days_since_positive <= 3:
                is_today_negative = today['close'] < today['open']
                if is_today_negative and today['close'] < start_positive_open:
                    matched_patterns.append("吞没阴线（1-3根最终吞没一根阳线）")
    
    # 15. 强转弱
    # 条件：
    # - 前一日为涨幅大于4%（主板）/6%（非主板）的阳线
    # - 今日为高开低走：开盘价>收盘价，C<2B，且(A==0或A<3B)
    # - 今日实体跌幅≥3%（相对开盘）
    # - 今日开盘价 > 前一日收盘价
    # - 今日收盘价 < (前一日开盘价 + 前一日收盘价) / 2
    is_prev_positive = prev_day['close'] > prev_day['open']
    if is_prev_positive:
        prev_change = (prev_day['close'] - prev_day['open']) / prev_day['open'] if prev_day['open'] > 0 else 0
        prev_change_pct = prev_change * 100
        
        is_main = KLinePatternService.is_main_board(stock_code)
        # 主板阈值改为3.5%，非主板仍为6%
        prev_change_threshold = 3.5 if is_main else 6.0
        
        if prev_change_pct > prev_change_threshold:
            is_today_negative = today['close'] < today['open']
            if is_today_negative:
                today_abc = KLinePatternService.calculate_abc(
                    today['open'], today['close'], today['high'], today['low']
                )
                
                # 高开低走形态约束
                if today_abc.c < 2 * today_abc.b and (today_abc.a == 0 or today_abc.a < 3 * today_abc.b):
                    # 实体跌幅（相对开盘）需 ≥ 3%
                    body_pct = ((today['open'] - today['close']) / today['open'] * 100) if today['open'] > 0 else 0
                    if body_pct >= 3.0:
                        # 高开且收盘位于前一日实体下半部分
                        prev_mid = (prev_day['open'] + prev_day['close']) / 2
                        if today['open'] > prev_day['close'] and today['close'] < prev_mid:
                            matched_patterns.append("强转弱")
    
    return matched_patterns


def batch_update_records(conn, updates: List[Dict]) -> int:
    """批量更新记录"""
    if not updates:
        return 0
    
    # 保活一次，避免长连接在批量更新前被踢掉
    try:
        conn.ping(reconnect=True)
    except Exception as e:
        logger.warning(f"⚠️ ping 主库失败: {e}")
    # 降低锁等待风险与卡死：缩短锁等待时间，分批提交
    try:
        cursor = conn.cursor()
        cursor.execute("SET SESSION innodb_lock_wait_timeout=5")
        conn.commit()
    except Exception as e:
        logger.warning(f"⚠️ 设置锁等待超时失败: {e}")
        cursor = conn.cursor()
    conn.autocommit(False)
    
    success_count = 0
    batch_size = 100
    last_commit_idx = 0
    
    for idx, update in enumerate(updates, 1):
        try:
            sql = """
                UPDATE b_daily_chance 
                SET volume_type = %s,
                    bullish_pattern = %s,
                    bearish_pattern = %s,
                    updated_at = NOW()
                WHERE stock_code = %s AND DATE(date) = %s
            """
            cursor.execute(sql, (
                update['volume_type'],
                update['bullish_pattern'],
                update['bearish_pattern'],
                update['stock_code'],
                update['date']
            ))
            success_count += 1
            
            # 分批提交，避免长事务卡住
            if idx % batch_size == 0:
                conn.commit()
                last_commit_idx = idx
                logger.info(f"  💾 分批提交进度: {idx}/{len(updates)}")
        except Exception as e:
            logger.debug(f"更新失败 {update['stock_code']} {update['date']}: {e}")
    
    # 提交剩余
    if last_commit_idx < len(updates):
        conn.commit()
    return success_count


def process_single_stock(master_conn, readonly_conn, stock: Dict, args) -> Dict:
    """处理单只股票的所有日期
    
    Args:
        master_conn: 生产主库连接（用于更新b_daily_chance）
        readonly_conn: 只读库连接（用于读取K线数据）
        stock: 股票信息
        args: 命令行参数
    """
    stock_code = (stock['code'] or '').upper()
    stock_name = stock['name']
    table_name = stock['table_name']
    
    result = {
        'code': stock_code,
        'name': stock_name,
        'total_dates': 0,
        'success_count': 0,
        'error_count': 0,
        'skip_count': 0
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"开始处理: {stock_code} ({stock_name})")
    logger.info(f"{'='*60}")
    
    # 检查 basic_data 表是否存在（在只读库中检查）
    try:
        cursor = readonly_conn.cursor()
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            logger.warning(f"  ⚠️ 表不存在: {table_name}")
            return result
    except Exception as e:
        logger.error(f"  ❌ 检查表失败: {e}")
        return result

    # ---------- 历史补齐（可选） ----------
    # 默认开启历史补齐；可用 --no-ensure-history 显式关闭
    ensure_history = bool(getattr(args, "ensure_history", True))
    history_start = getattr(args, "history_start", DEFAULT_HISTORY_START) or DEFAULT_HISTORY_START
    history_end = getattr(args, "history_end", "") or datetime.now().strftime("%Y-%m-%d")
    fill_placeholders = bool(getattr(args, "fill_placeholders", False))

    dates: List[str] = []
    if ensure_history:
        # 用只读库日K表作为“交易日清单”
        try:
            trading_dates = get_trading_dates_from_basic_data(readonly_conn, table_name, history_start, history_end)
        except Exception as e:
            logger.warning(f"  ⚠️ 获取交易日失败: {e}")
            trading_dates = []

        if not trading_dates:
            logger.info(f"  ℹ️ {stock_code} 在K线表中无交易日数据（{history_start}~{history_end}）")
            return result

        # 先对比 b_daily_chance 是否齐全，不齐则先拉接口回填
        existing_dates = get_existing_dates_in_b_daily_chance(master_conn, stock_code, history_start, history_end)
        missing_dates = [d for d in trading_dates if d not in existing_dates]
        result["required_dates"] = len(trading_dates)
        result["missing_before"] = len(missing_dates)

        if missing_dates:
            logger.info(f"  缺失历史记录: {len(missing_dates)} 天，将调用接口回填（{history_start}~{history_end}）")
            stock_nature = get_stock_nature_from_all_stock(master_conn, stock_code)
            try:
                upserted = upsert_scores_support_pressure_from_api(
                    master_conn, stock_code, stock_name, stock_nature, history_start, history_end
                )
            except Exception as e:
                logger.warning(f"  ⚠️ 接口回填失败: {e}")
                upserted = 0

            result["api_upsert_rows"] = upserted

            # 复查缺失
            existing_dates = get_existing_dates_in_b_daily_chance(master_conn, stock_code, history_start, history_end)
            missing_after = [d for d in trading_dates if d not in existing_dates]
            result["missing_after_api"] = len(missing_after)

            if missing_after and fill_placeholders:
                inserted = insert_placeholders_if_missing(
                    master_conn, stock_code, stock_name, stock_nature, missing_after
                )
                result["placeholders_inserted"] = inserted
                existing_dates = get_existing_dates_in_b_daily_chance(master_conn, stock_code, history_start, history_end)

        # 最终用于更新量型/形态的日期：交易日 ∩ b_daily_chance 已存在日期
        dates = [d for d in trading_dates if d in existing_dates]
        result['total_dates'] = len(dates)
    else:
        # 不启用补齐：沿用老逻辑（仅处理 b_daily_chance 已有日期）
        dates = get_all_dates_for_stock(master_conn, stock_code)
        result['total_dates'] = len(dates)

    if not dates:
        logger.info(f"  ℹ️ {stock_code} 无可处理日期（ensure_history={ensure_history}）")
        return result
    
    logger.info(f"  📅 需要处理 {len(dates)} 个交易日")
    logger.info(f"  📅 日期范围: {dates[0]} ~ {dates[-1]}")
    
    # 一次性获取所有日线数据（从只读库，多取20天历史数据用于计算）
    start_date_obj = datetime.strptime(dates[0], '%Y-%m-%d') - timedelta(days=20)
    start_date = start_date_obj.strftime('%Y-%m-%d')
    end_date = dates[-1]
    
    logger.info(f"  📊 获取K线数据: {start_date} ~ {end_date}")
    daily_data = get_daily_data_batch(readonly_conn, table_name, start_date, end_date)
    
    if not daily_data:
        logger.warning(f"  ⚠️ 无法获取K线数据")
        return result
    
    logger.info(f"  📊 获取到 {len(daily_data)} 条K线数据")
    
    # 建立日期到索引的映射
    date_to_idx = {}
    for i, day in enumerate(daily_data):
        day_date = day['date']
        if isinstance(day_date, datetime):
            date_str = day_date.strftime('%Y-%m-%d')
        else:
            date_str = str(day_date)
        date_to_idx[date_str] = i
    
    # 第一轮：批量计算所有成交量类型（因为多头组合需要用到）
    logger.info(f"  🔄 第一轮：计算成交量类型...")
    volume_type_cache = {}
    for i in range(len(daily_data)):
        volume_type = calculate_volume_type_for_idx(daily_data, i)
        if volume_type:
            volume_type_cache[i] = volume_type
    
    # 第二轮：计算多空头组合并准备更新
    logger.info(f"  🔄 第二轮：计算多空头组合并更新...")
    updates = []
    start_time = time.time()
    
    for i, date_str in enumerate(dates, 1):
        try:
            idx = date_to_idx.get(date_str)
            if idx is None:
                result['skip_count'] += 1
                continue
            
            # 获取成交量类型
            volume_type = volume_type_cache.get(idx, '')
            
            # 计算多头组合
            bullish_patterns = identify_bullish_patterns(stock_code, daily_data, idx, volume_type_cache)
            bullish_pattern = ','.join(bullish_patterns) if bullish_patterns else ''
            
            # 计算空头组合
            bearish_patterns = identify_bearish_patterns(stock_code, daily_data, idx)
            bearish_pattern = ','.join(bearish_patterns) if bearish_patterns else ''
            
            updates.append({
                'stock_code': stock_code,
                'date': date_str,
                'volume_type': volume_type or '',
                'bullish_pattern': bullish_pattern,
                'bearish_pattern': bearish_pattern
            })
            
            # 进度输出
            if i % 50 == 0 or i == len(dates):
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = avg_time * (len(dates) - i)
                print(f"\r  [{i}/{len(dates)}] {i*100//len(dates)}% | "
                      f"耗时: {elapsed:.1f}s | 预计剩余: {remaining:.1f}s", 
                      end='', flush=True)
            
        except Exception as e:
            result['error_count'] += 1
            logger.debug(f"  处理失败 {date_str}: {e}")
    
    print()  # 换行
    
    # 批量更新数据库（使用主库连接）
    if updates:
        logger.info(f"  💾 批量更新 {len(updates)} 条记录...")
        result['success_count'] = batch_update_records(master_conn, updates)
    
    logger.info(f"  ✅ {stock_code} 完成: 成功={result['success_count']}, "
                f"跳过={result['skip_count']}, 错误={result['error_count']}")
    
    return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='刷新 b_daily_chance 表的成交量类型和多空头组合'
    )
    parser.add_argument('--test', action='store_true', 
                        help='测试模式：只处理前5支股票')
    parser.add_argument('--all', action='store_true', 
                        help='处理全部股票')
    parser.add_argument('--codes', type=str, 
                        help='指定股票代码，逗号分隔（如: SZ301565,SH688701）')
    parser.add_argument('--limit', type=int, default=5,
                        help='限制处理的股票数量（默认5个，用于测试）')
    parser.add_argument('--from-json', action='store_true',
                        help='从 stock_config.json 读取股票列表（而不是 stock_list.csv）')
    ensure_history_group = parser.add_mutually_exclusive_group()
    ensure_history_group.add_argument('--ensure-history', action='store_true', default=True,
                                      help='检查并补齐 b_daily_chance 历史记录（默认开启）')
    ensure_history_group.add_argument('--no-ensure-history', action='store_false', dest='ensure_history',
                                      help='关闭历史补齐（仅处理 b_daily_chance 已有日期，不调用接口）')
    parser.add_argument('--history-start', type=str, default=DEFAULT_HISTORY_START,
                        help=f'历史开始日期 YYYY-MM-DD（默认 {DEFAULT_HISTORY_START}）')
    parser.add_argument('--history-end', type=str, default='',
                        help='历史结束日期 YYYY-MM-DD（默认今天）')
    parser.add_argument('--fill-placeholders', action='store_true',
                        help='若接口回填后仍有缺失交易日，则插入占位记录补齐日期（谨慎使用）')
    args = parser.parse_args()

    # 参数校验
    if args.ensure_history:
        try:
            datetime.strptime(args.history_start, "%Y-%m-%d")
        except Exception:
            logger.error(f"❌ history-start 日期格式错误: {args.history_start}（应为 YYYY-MM-DD）")
            return
        if args.history_end:
            try:
                datetime.strptime(args.history_end, "%Y-%m-%d")
            except Exception:
                logger.error(f"❌ history-end 日期格式错误: {args.history_end}（应为 YYYY-MM-DD）")
                return
    
    # 检查服务是否可用
    if not KLINE_SERVICE_AVAILABLE:
        logger.warning("⚠️ KLinePatternService 不可用，多空头组合将不会计算")
    
    logger.info("=" * 80)
    logger.info("🚀 开始刷新 b_daily_chance 表（成交量类型 + 多空头组合）")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"生产主库: {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
    logger.info("=" * 80)
    
    # 加载股票列表
    if args.from_json:
        all_stocks = load_stock_list_from_json()
    else:
        all_stocks = load_stock_list_from_csv()
    
    if not all_stocks:
        logger.error("❌ 无法加载股票列表")
        return
    
    # 确定要处理的股票
    if args.codes:
        # 指定股票代码
        specified_codes = [c.strip().upper() for c in args.codes.split(',')]
        stocks = [s for s in all_stocks if s['code'].upper() in specified_codes]
        if not stocks:
            logger.error(f"❌ 未找到指定的股票: {args.codes}")
            return
    elif args.all:
        stocks = all_stocks
    else:
        # 默认或测试模式
        limit = args.limit if args.test else 5
        stocks = all_stocks[:limit]
        logger.info(f"📊 测试模式：处理前 {limit} 支股票")
    
    logger.info("-" * 80)
    logger.info("将处理以下股票：")
    for s in stocks[:10]:  # 最多显示10个
        logger.info(f"  - {s['code']} ({s['name']})")
    if len(stocks) > 10:
        logger.info(f"  ... 还有 {len(stocks) - 10} 支股票")
    logger.info("-" * 80)
    
    # 连接数据库
    try:
        master_conn = get_master_connection()
        logger.info(f"✅ 已连接生产主库: {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
        readonly_conn = get_readonly_connection()
        logger.info(f"✅ 已连接只读库: {READONLY_DB_CONFIG['host']}:{READONLY_DB_CONFIG['port']}")
    except Exception as e:
        logger.error(f"❌ 连接数据库失败: {e}")
        return
    
    # 处理每只股票
    total_results = {
        'total_stocks': len(stocks),
        'success_stocks': 0,
        'total_dates': 0,
        'total_success': 0,
        'total_errors': 0
    }
    
    start_time = time.time()
    
    try:
        for i, stock in enumerate(stocks, 1):
            logger.info(f"\n[{i}/{len(stocks)}] 处理 {stock['code']} ({stock['name']})...")
            
            try:
                result = process_single_stock(master_conn, readonly_conn, stock, args)
                
                total_results['total_dates'] += result['total_dates']
                total_results['total_success'] += result['success_count']
                total_results['total_errors'] += result['error_count']
                
                if result['success_count'] > 0:
                    total_results['success_stocks'] += 1
                    
            except Exception as e:
                logger.error(f"❌ 处理 {stock['code']} 失败: {e}")
                
    finally:
        master_conn.close()
        readonly_conn.close()
        logger.info("\n✅ 已断开所有数据库连接")
    
    # 输出总结
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("📊 处理完成总结")
    logger.info("=" * 80)
    logger.info(f"  总股票数: {total_results['total_stocks']}")
    logger.info(f"  成功股票: {total_results['success_stocks']}")
    logger.info(f"  总日期数: {total_results['total_dates']}")
    logger.info(f"  成功更新: {total_results['total_success']}")
    logger.info(f"  错误数量: {total_results['total_errors']}")
    logger.info(f"  总耗时: {elapsed:.1f} 秒")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
