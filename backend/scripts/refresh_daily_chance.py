"""
统一刷新脚本：刷新 b_daily_chance 表的最新一天数据

功能：
1. 从API获取数据：赔率分数、支撑线、压力线
2. 计算数据：成交量类型、多头组合、空头组合
3. 写入生产主库

配置：
- USE_59_STOCKS = True   使用59支代表性股票
- USE_59_STOCKS = False  使用全部股票（约5000支）

使用方式：
- 直接运行：python refresh_daily_chance.py
- 立即执行：python refresh_daily_chance.py --now
- 定时任务：python refresh_daily_chance.py --scheduler
"""
import sys
import os
import re
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

# 添加路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

import pymysql
import requests

# ============ 配置区域 ============
# 切换股票范围：True=59支代表性股票，False=全部股票
USE_59_STOCKS = False

# 生产主库配置（只有主库才能写入）
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}

# 外部API配置
API_BASE_URL = "http://121.5.174.81:8005"

# ============ 配置结束 ============

# 配置日志
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置 root logger 确保输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'refresh_daily_chance.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('refresh_daily_chance')
logger.setLevel(logging.INFO)

# 导入计算服务
try:
    from domain.services.bullish_pattern_service import BullishPatternService
    from domain.services.bearish_pattern_service import BearishPatternService
    from domain.services.volume_type_service import VolumeTypeService
    SERVICES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"计算服务导入失败: {e}")
    SERVICES_AVAILABLE = False


def get_master_connection():
    """获取生产主库连接"""
    return pymysql.connect(**MASTER_DB_CONFIG)


def load_59_stocks() -> List[Dict]:
    """加载59支代表性股票"""
    config_path = os.path.join(backend_dir, 'infrastructure/config/stock_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    stocks = []
    for nature, stock_list in config.items():
        for stock in stock_list:
            stocks.append({
                'code': stock['code'],
                'name': stock['name'],
                'nature': nature,
                'table_name': f"basic_data_{stock['code'].lower()}"
            })
    
    return stocks


def load_all_stocks(conn) -> List[Dict]:
    """从数据库加载全部活跃股票"""
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    sql = """
        SELECT code, name, nature
        FROM all_stock
        WHERE (`是否退市` != 1 OR `是否退市` IS NULL)
        ORDER BY code
    """
    
    cursor.execute(sql)
    results = cursor.fetchall()
    
    stocks = []
    for row in results:
        stocks.append({
            'code': row['code'],
            'name': row['name'],
            'nature': row.get('nature') or '波段',
            'table_name': f"basic_data_{row['code'].lower()}"
        })
    
    return stocks


def fetch_daily_chance_from_api(stock_code: str) -> Optional[Dict]:
    """从API获取最新一天的每日机会数据"""
    try:
        url = f"{API_BASE_URL}/stock/getDailyChanceWithBeauty"
        
        response = requests.post(
            url,
            data=stock_code,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]  # 返回最新一天的数据
        return None
        
    except Exception as e:
        logger.debug(f"API获取失败: {stock_code}, {e}")
        return None


def parse_win_ratio_description(description: str) -> Tuple[float, float, float]:
    """解析赔率描述，返回：日线赔率、周线赔率、总分"""
    day_score = 0.0
    week_score = 0.0
    total_score = 0.0
    
    if not description:
        return day_score, week_score, total_score
    
    try:
        day_match = re.search(r'日线赔率得分[：:]\s*([\d.]+)', description)
        if day_match:
            day_score = float(day_match.group(1))
        
        week_match = re.search(r'周线赔率得分[：:]\s*([\d.]+)', description)
        if week_match:
            week_score = float(week_match.group(1))
        
        total_match = re.search(r'赔率总分[：:]\s*([\d.]+)', description)
        if total_match:
            total_score = float(total_match.group(1))
    except:
        pass
    
    return day_score, week_score, total_score


def calculate_volume_type(table_name: str, volume: float) -> str:
    """计算成交量类型"""
    if not SERVICES_AVAILABLE or not volume:
        return ''
    
    try:
        volume_type = VolumeTypeService.calculate_volume_type_with_predicted(table_name, volume)
        return volume_type if volume_type else ''
    except Exception as e:
        logger.debug(f"计算成交量类型失败: {table_name}, {e}")
        return ''


def try_append_volume_s(conn, table_name: str, current_volume: float) -> bool:
    """
    兜底判定S型量：当日成交量 >= 前一日成交量的1.2倍则视为S
    仅在量型中尚未包含S时补充，避免遗漏。
    """
    if not current_volume or current_volume <= 0:
        return False
    try:
        cursor = conn.cursor()
        sql = f"""
            SELECT cheng_jiao_liang
            FROM `{table_name}`
            WHERE peroid_type = '1day'
            ORDER BY shi_jian DESC
            LIMIT 2
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        # rows[0] 是最近一条（通常是昨日），rows[1] 更早
        if rows and len(rows) >= 1:
            prev_volume = rows[0][0] if rows[0] and len(rows[0]) >= 1 else None
            if prev_volume and prev_volume > 0:
                ratio = current_volume / prev_volume
                return ratio >= 1.2
    except Exception as e:
        logger.debug(f"S型量兜底判定失败: {table_name}, {e}")
    return False


def calculate_patterns(stock_code: str, table_name: str, date_str: str) -> Tuple[str, str]:
    """计算多头和空头组合"""
    bullish_pattern = ''
    bearish_pattern = ''
    
    if not SERVICES_AVAILABLE:
        return bullish_pattern, bearish_pattern
    
    try:
        # 将字符串日期转换为 datetime 对象
        # 支持格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
        date_only = date_str.split(' ')[0] if ' ' in date_str else date_str
        target_date = datetime.strptime(date_only, '%Y-%m-%d')
        
        # 计算多头组合
        bullish_patterns = BullishPatternService.identify_bullish_patterns(
            stock_code=stock_code,
            table_name=table_name,
            target_date=target_date
        )
        bullish_pattern = ','.join(bullish_patterns) if bullish_patterns else ''
        
        # 计算空头组合
        bearish_patterns = BearishPatternService.identify_bearish_patterns(
            stock_code=stock_code,
            table_name=table_name,
            target_date=target_date
        )
        bearish_pattern = ','.join(bearish_patterns) if bearish_patterns else ''
        
    except ValueError as e:
        logger.debug(f"日期格式错误: {stock_code} {date_str}, {e}")
    except Exception as e:
        logger.debug(f"计算K线组合失败: {stock_code}, {e}")
    
    return bullish_pattern, bearish_pattern


def process_stock(conn, stock: Dict) -> bool:
    """
    处理单只股票：获取API数据 + 计算数据 + 写入数据库
    
    Returns:
        是否成功
    """
    stock_code = stock['code']
    stock_name = stock['name']
    stock_nature = stock['nature']
    table_name = stock['table_name']
    
    try:
        # 1. 从API获取数据
        api_data = fetch_daily_chance_from_api(stock_code)
        if not api_data:
            logger.debug(f"  跳过（无API数据）: {stock_code}")
            return False
        
        # 2. 解析API数据
        date_str = api_data.get('day', '')
        if not date_str:
            return False
        date_only = date_str.split(' ')[0] if ' ' in date_str else date_str
        
        # 成交量
        day_seg = api_data.get('daySeg', {})
        volume = day_seg.get('chengJiaoLiang', 0) if day_seg else 0
        volume_for_calc = volume / 100 if volume else 0
        
        # 支撑线、压力线
        support_price = api_data.get('supportPrice')
        pressure_price = api_data.get('pressurePrice')
        support_price_int = int(float(support_price)) if support_price else None
        pressure_price_int = int(float(pressure_price)) if pressure_price else None
        
        # 赔率分数
        win_ratio_desc = api_data.get('winRatioDescription', '')
        day_win_ratio, week_win_ratio, total_win_ratio = parse_win_ratio_description(win_ratio_desc)
        
        # 3. 计算数据
        volume_type = calculate_volume_type(table_name, volume_for_calc)
        # 兜底补S型：如果量型里没有S，且当日量是前一日的1.2倍，则补充S
        if volume_type:
            volume_types = [t.strip() for t in volume_type.split(',') if t.strip()]
        else:
            volume_types = []
        if 'S' not in volume_types and try_append_volume_s(conn, table_name, volume):
            volume_types.append('S')
        volume_type = ','.join(volume_types) if volume_types else ''
        bullish_pattern, bearish_pattern = calculate_patterns(stock_code, table_name, date_only)
        
        # 4. 写入数据库（UPSERT）
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO b_daily_chance 
            (stock_code, stock_name, stock_nature, date, 
             day_win_ratio_score, week_win_ratio_score, total_win_ratio_score,
             support_price, pressure_price, volume_type, 
             bullish_pattern, bearish_pattern, updated_at)
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
        
        cursor.execute(sql, (
            stock_code, stock_name, stock_nature, date_only,
            day_win_ratio, week_win_ratio, total_win_ratio,
            support_price_int, pressure_price_int, volume_type,
            bullish_pattern, bearish_pattern
        ))
        conn.commit()
        
        logger.info(f"  ✅ {stock_code} {stock_name} | "
                   f"日期:{date_only} | 赔率:{total_win_ratio:.1f} | "
                   f"量型:{volume_type or '-'} | "
                   f"多头:{bullish_pattern or '-'} | 空头:{bearish_pattern or '-'}")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ {stock_code} 处理失败: {e}")
        return False


def refresh_job():
    """主任务：刷新 b_daily_chance 表"""
    logger.info("=" * 80)
    logger.info("🚀 开始刷新 b_daily_chance 表（最新一天数据）")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"股票范围: {'59支代表性股票' if USE_59_STOCKS else '全部股票'}")
    logger.info(f"主库地址: {MASTER_DB_CONFIG['host']}:{MASTER_DB_CONFIG['port']}")
    logger.info("=" * 80)
    
    # 连接主库
    try:
        conn = get_master_connection()
        logger.info("✅ 已连接生产主库")
    except Exception as e:
        logger.error(f"❌ 连接主库失败: {e}")
        return
    
    try:
        # 加载股票列表
        if USE_59_STOCKS:
            stocks = load_59_stocks()
        else:
            stocks = load_all_stocks(conn)
        
        logger.info(f"📊 共需处理 {len(stocks)} 支股票")
        logger.info("-" * 80)
        
        # 处理每只股票
        success_count = 0
        failed_stocks = []
        
        for i, stock in enumerate(stocks, 1):
            logger.info(f"[{i}/{len(stocks)}] 处理 {stock['code']} ({stock['name']})...")
            
            if process_stock(conn, stock):
                success_count += 1
            else:
                failed_stocks.append(stock['code'])
        
        # 汇总结果
        logger.info("=" * 80)
        logger.info("✅ 刷新任务完成")
        logger.info(f"成功: {success_count}/{len(stocks)} 支")
        logger.info(f"失败: {len(failed_stocks)} 支")
        if failed_stocks and len(failed_stocks) <= 20:
            logger.info(f"失败列表: {', '.join(failed_stocks)}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 任务执行失败: {e}", exc_info=True)
    finally:
        conn.close()


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description='刷新 b_daily_chance 表的最新一天数据')
    parser.add_argument('--now', action='store_true', help='立即执行一次')
    parser.add_argument('--scheduler', action='store_true', help='启动定时任务（每天16:00执行）')
    parser.add_argument('--all', action='store_true', help='处理全部股票（覆盖配置）')
    parser.add_argument('--59', action='store_true', dest='use_59', help='只处理59支股票（覆盖配置）')
    args = parser.parse_args()
    
    # 覆盖配置
    global USE_59_STOCKS
    if args.all:
        USE_59_STOCKS = False
    elif args.use_59:
        USE_59_STOCKS = True
    
    if args.scheduler:
        # 定时任务模式
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.error("❌ APScheduler 未安装，请运行: pip install APScheduler")
            sys.exit(1)
        
        logger.info("🌟 启动定时任务模式")
        logger.info(f"执行时间: 每天 16:00")
        logger.info(f"股票范围: {'59支' if USE_59_STOCKS else '全部'}")
        
        scheduler = BlockingScheduler()
        scheduler.add_job(
            refresh_job,
            trigger=CronTrigger(hour=16, minute=0),
            id='refresh_daily_chance',
            name='刷新每日机会数据',
            replace_existing=True
        )
        
        try:
            logger.info("✅ 定时任务已启动，等待执行...")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("⛔ 定时任务已停止")
            scheduler.shutdown()
    else:
        # 立即执行
        refresh_job()


if __name__ == '__main__':
    main()
