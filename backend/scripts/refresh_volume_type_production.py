"""
刷新生产库 b_daily_chance 表最近3个月的数据

功能说明：
1. 连接生产主库
2. 从 stock_list.csv 读取股票列表
3. 从 basic_stock_股票代码 表获取日K线数据（period_type='1day'）
4. 更新 b_daily_chance 表的以下字段：
   - volume_type: 成交量类型
   - bullish_pattern: 多头K线组合
   - bearish_pattern: 空头K线组合

定时任务：每天下午5点执行
"""
import sys
import os
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pymysql
import pymysql.cursors

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

# 日志配置（先配置日志，再导入其他模块）
import logging
log_dir = os.path.join(script_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, 'refresh_volume_type.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 生产主库配置（直接导入）
from config_production_master import DATABASE_CONFIG

# 导入K线组合服务
try:
    from domain.services.bullish_pattern_service import BullishPatternService
    from domain.services.bearish_pattern_service import BearishPatternService
    PATTERN_SERVICES_AVAILABLE = True
    logger.info("K线组合服务导入成功")
except ImportError as e:
    logger.warning(f"K线组合服务导入失败: {e}")
    PATTERN_SERVICES_AVAILABLE = False


def get_production_connection():
    """获取生产主库连接"""
    return pymysql.connect(
        host=DATABASE_CONFIG['host'],
        port=DATABASE_CONFIG['port'],
        user=DATABASE_CONFIG['user'],
        password=DATABASE_CONFIG['password'],
        database=DATABASE_CONFIG['database'],
        charset=DATABASE_CONFIG.get('charset', 'utf8mb4'),
        autocommit=True
    )


def load_stock_list(csv_path: str) -> List[Dict[str, str]]:
    """
    从CSV文件加载股票列表
    
    Returns:
        股票列表，每个元素为 {'code': 'SZ301565', 'name': '中仑新材'}
    """
    stocks = []
    # 尝试不同的编码方式
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 处理可能的BOM字符
                    code_key = 'code' if 'code' in row else list(row.keys())[0]
                    name_key = 'name' if 'name' in row else list(row.keys())[1]
                    stocks.append({
                        'code': row[code_key].strip(),
                        'name': row[name_key].strip()
                    })
            if stocks:
                logger.info(f"使用编码 {encoding} 成功读取CSV文件")
                return stocks
        except Exception as e:
            logger.debug(f"使用编码 {encoding} 读取失败: {e}")
            stocks = []
            continue
    
    raise Exception(f"无法读取CSV文件: {csv_path}")
    return stocks


def get_daily_volumes(conn, table_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    获取指定日期范围内的日线成交量数据
    
    Args:
        conn: 数据库连接
        table_name: 股票表名 (如 basic_stock_SZ301565)
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        日线数据列表，包含date和volume字段
    """
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 检查表是否存在
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            logger.warning(f"表不存在: {table_name}")
            return []
        
        query = f"""
            SELECT shi_jian as date, cheng_jiao_liang as volume
            FROM {table_name}
            WHERE peroid_type = '1day' 
              AND shi_jian >= %s 
              AND shi_jian <= %s
            ORDER BY shi_jian ASC
        """
        
        cursor.execute(query, (start_date, end_date))
        results = cursor.fetchall()
        
        return [
            {
                'date': row['date'],
                'volume': int(row['volume']) / 100 if row['volume'] else 0  # 数据库存储需要除以100
            }
            for row in results
        ]
        
    except Exception as e:
        logger.error(f"获取日线成交量数据失败: {table_name}: {e}")
        return []


def check_abc_volume_type(daily_data: List[Dict], idx: int) -> Optional[str]:
    """
    检查指定索引位置的成交量是否为A/B/C类型
    """
    if idx < 1:
        return None
    
    target_volume = daily_data[idx]['volume']
    
    # 检查类型A: 当日为前1日成交均量的2倍-3倍
    if idx >= 1:
        prev_volume = daily_data[idx - 1]['volume']
        if prev_volume > 0:
            ratio = target_volume / prev_volume
            if 2.0 <= ratio <= 3.0:
                return 'A'
    
    # 检查类型B: 当日为前3日成交均量的2倍及以上
    if idx >= 3:
        prev_3_volumes = [daily_data[i]['volume'] for i in range(idx - 3, idx)]
        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                return 'B'
    
    # 检查类型C: 当日为前5日成交均量的2倍及以上
    if idx >= 5:
        prev_5_volumes = [daily_data[i]['volume'] for i in range(idx - 5, idx)]
        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
        if avg_volume > 0:
            ratio = target_volume / avg_volume
            if ratio >= 2.0:
                return 'C'
    
    return None


def check_all_volume_types(daily_data: List[Dict], idx: int) -> Optional[str]:
    """
    检查指定索引位置的成交量是否为A/B/C/D类型（返回所有匹配的类型）
    """
    if idx < 1:
        return None
    
    target_volume = daily_data[idx]['volume']
    matched_types = []
    
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
    
    # 检查类型D（需要检查前5天是否有ABC放量）
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
        seen = set()
        unique_types = []
        for t in ['A', 'B', 'C', 'D']:
            if t in matched_types and t not in seen:
                unique_types.append(t)
                seen.add(t)
        return ','.join(unique_types)
    
    return None


def calculate_volume_type(daily_data: List[Dict], target_idx: int) -> Optional[str]:
    """
    计算指定索引位置的成交量类型
    
    Args:
        daily_data: 日线数据列表（已排序，从旧到新）
        target_idx: 目标日期的索引
        
    Returns:
        成交量类型: 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z' 或多个类型用逗号连接
    """
    if target_idx is None or target_idx < 1:
        return None
    
    target_volume = daily_data[target_idx]['volume']
    matched_types = []
    
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
    
    # 计算类型D: 前五日出现过ABC任意一种放量，标记为X日，今日的成交量为X日的1.2倍以上
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
    
    # 计算类型F: 前五日出现过ABCD任意一种放量，今日成交量为X日的3倍以上，或为前5日均值的3倍以上
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
    
    # 计算类型G: 前五日出现ABCD放量，今日量能为X日的0.7倍及以上
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
    
    # 计算类型H: 前五日出现ABCD放量，今日量能大于X日
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
    
    # 计算类型Z: 前10日出现ABC放量，昨日量能相较于前三日均量1.3倍以上，今日量相较于昨日1.08倍以上
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
        for t in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z']:
            if t in matched_types and t not in seen:
                unique_types.append(t)
                seen.add(t)
        return ','.join(unique_types)
    
    return None


def get_daily_chance_dates(conn, stock_code: str, start_date: str, end_date: str) -> List[datetime]:
    """
    获取 b_daily_chance 表中指定股票在日期范围内的所有日期
    """
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        sql = """
            SELECT date FROM b_daily_chance 
            WHERE stock_code = %s AND date BETWEEN %s AND %s
            ORDER BY date ASC
        """
        cursor.execute(sql, (stock_code, start_date, end_date))
        results = cursor.fetchall()
        
        return [row['date'] for row in results]
        
    except Exception as e:
        logger.error(f"获取daily_chance日期失败: {stock_code}: {e}")
        return []


def update_volume_type_batch(conn, updates: List[Tuple[str, str, str]]) -> int:
    """
    批量更新 b_daily_chance 表的 volume_type
    
    Args:
        conn: 数据库连接
        updates: 更新列表，每个元素为 (stock_code, date, volume_type)
        
    Returns:
        更新的记录数
    """
    if not updates:
        return 0
    
    try:
        cursor = conn.cursor()
        
        sql = """
            UPDATE b_daily_chance 
            SET volume_type = %s
            WHERE stock_code = %s AND date = %s
        """
        
        cursor.executemany(sql, [(vt, sc, d) for sc, d, vt in updates])
        updated_count = cursor.rowcount
        
        return updated_count
        
    except Exception as e:
        logger.error(f"批量更新成交量类型失败: {e}")
        return 0


def update_patterns_batch(conn, updates: List[Tuple[str, str, str, str]]) -> int:
    """
    批量更新 b_daily_chance 表的 bullish_pattern 和 bearish_pattern
    
    Args:
        conn: 数据库连接
        updates: 更新列表，每个元素为 (stock_code, date, bullish_pattern, bearish_pattern)
        
    Returns:
        更新的记录数
    """
    if not updates:
        return 0
    
    try:
        cursor = conn.cursor()
        
        sql = """
            UPDATE b_daily_chance 
            SET bullish_pattern = %s, bearish_pattern = %s
            WHERE stock_code = %s AND date = %s
        """
        
        cursor.executemany(sql, [(bp, bep, sc, d) for sc, d, bp, bep in updates])
        updated_count = cursor.rowcount
        
        return updated_count
        
    except Exception as e:
        logger.error(f"批量更新K线组合失败: {e}")
        return 0


def get_stock_table_name(stock_code: str) -> str:
    """
    根据股票代码获取K线数据表名
    
    Args:
        stock_code: 股票代码，如 SZ301565, SH600000
        
    Returns:
        表名，如 basic_data_sz301565, basic_data_sh600000
    """
    # 转换为: basic_data_ + 小写股票代码
    # SZ301565 -> basic_data_sz301565
    # SH600000 -> basic_data_sh600000
    return f"basic_data_{stock_code.lower()}"


def process_stock(conn, stock_code: str, stock_name: str, start_date: datetime, end_date: datetime) -> Tuple[int, int]:
    """
    处理单只股票的成交量类型和K线组合计算
    
    Returns:
        (成交量类型更新数, K线组合更新数)
    """
    table_name = get_stock_table_name(stock_code)
    
    # 获取 b_daily_chance 表中该股票在日期范围内的所有日期
    chance_dates = get_daily_chance_dates(
        conn, stock_code, 
        start_date.strftime('%Y-%m-%d'), 
        end_date.strftime('%Y-%m-%d')
    )
    
    if not chance_dates:
        logger.debug(f"股票 {stock_code} 在 b_daily_chance 表中没有需要更新的数据")
        return 0, 0
    
    # 获取足够的历史数据（需要前15天的数据，因为Z类型需要前10天）
    data_start_date = start_date - timedelta(days=20)
    
    # 获取日K线数据
    daily_data = get_daily_volumes(conn, table_name, data_start_date, end_date)
    
    if not daily_data or len(daily_data) < 2:
        logger.warning(f"股票 {stock_code} 历史数据不足")
        return 0, 0
    
    # 按日期排序
    daily_data.sort(key=lambda x: x['date'])
    
    # 为每个日期计算成交量类型和K线组合
    volume_updates = []
    pattern_updates = []
    
    for target_date in chance_dates:
        # 处理日期格式
        if isinstance(target_date, datetime):
            target_date_obj = target_date
            target_date_cmp = target_date.date()
        else:
            target_date_obj = datetime.combine(target_date, datetime.min.time())
            target_date_cmp = target_date
        
        date_str = target_date_obj.strftime('%Y-%m-%d')
        
        # 在daily_data中找到目标日期的索引
        target_idx = None
        for i, data in enumerate(daily_data):
            data_date = data['date']
            # 处理日期格式
            if isinstance(data_date, datetime):
                data_date = data_date.date()
            
            if data_date == target_date_cmp:
                target_idx = i
                break
        
        if target_idx is None or target_idx < 1:
            continue
        
        # 1. 计算成交量类型
        volume_type = calculate_volume_type(daily_data, target_idx)
        if volume_type:
            volume_updates.append((stock_code, date_str, volume_type))
        
        # 2. 计算K线组合（如果服务可用）
        if PATTERN_SERVICES_AVAILABLE:
            try:
                # 计算多头组合
                bullish_patterns = BullishPatternService.identify_bullish_patterns(
                    stock_code=stock_code,
                    table_name=table_name,
                    target_date=target_date_obj
                )
                bullish_pattern_str = ','.join(bullish_patterns) if bullish_patterns else ''
                
                # 计算空头组合
                bearish_patterns = BearishPatternService.identify_bearish_patterns(
                    stock_code=stock_code,
                    table_name=table_name,
                    target_date=target_date_obj
                )
                bearish_pattern_str = ','.join(bearish_patterns) if bearish_patterns else ''
                
                # 只要有数据就更新（包括空字符串，表示没有组合）
                pattern_updates.append((stock_code, date_str, bullish_pattern_str, bearish_pattern_str))
                
            except Exception as e:
                logger.debug(f"计算K线组合失败: {stock_code} {date_str}: {e}")
    
    # 批量更新
    volume_count = 0
    pattern_count = 0
    
    if volume_updates:
        volume_count = update_volume_type_batch(conn, volume_updates)
    
    if pattern_updates:
        pattern_count = update_patterns_batch(conn, pattern_updates)
    
    return volume_count, pattern_count


def refresh_job(test_limit: int = 0, days: int = 90):
    """
    定时任务：刷新成交量类型和K线组合
    
    Args:
        test_limit: 测试模式，只处理前N只股票，0表示处理全部
        days: 刷新最近N天的数据，默认90天（3个月）
    """
    # 确保日志目录存在
    log_dir = os.path.join(script_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info("开始刷新生产库 b_daily_chance 表的数据")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("刷新内容: volume_type（成交量类型）、bullish_pattern（多头组合）、bearish_pattern（空头组合）")
    if test_limit > 0:
        logger.info(f"【测试模式】只处理前 {test_limit} 只股票")
    logger.info("=" * 70)
    
    # 设置日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    logger.info(f"日期范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')} ({days}天)")
    
    # 加载股票列表
    csv_path = os.path.join(project_root, 'stock_list.csv')
    if not os.path.exists(csv_path):
        logger.error(f"股票列表文件不存在: {csv_path}")
        return
    
    stocks = load_stock_list(csv_path)
    
    # 测试模式：只处理前N只股票
    if test_limit > 0:
        stocks = stocks[:test_limit]
    
    logger.info(f"从 stock_list.csv 加载了 {len(stocks)} 只股票")
    
    # 连接生产主库
    try:
        conn = get_production_connection()
        logger.info(f"成功连接生产主库: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}")
    except Exception as e:
        logger.error(f"连接生产主库失败: {e}")
        return
    
    # 统计信息
    total_volume_updated = 0
    total_pattern_updated = 0
    success_count = 0
    failed_stocks = []
    skipped_stocks = []
    
    try:
        # 处理每只股票
        for i, stock in enumerate(stocks, 1):
            stock_code = stock['code']
            stock_name = stock['name']
            
            if i % 100 == 0 or i == 1:
                logger.info(f"\n进度: [{i}/{len(stocks)}] 正在处理: {stock_code} ({stock_name})")
            
            try:
                volume_count, pattern_count = process_stock(conn, stock_code, stock_name, start_date, end_date)
                
                if volume_count > 0 or pattern_count > 0:
                    total_volume_updated += volume_count
                    total_pattern_updated += pattern_count
                    success_count += 1
                    if i % 100 == 0:
                        logger.info(f"  更新: 成交量类型 {volume_count} 条, K线组合 {pattern_count} 条")
                else:
                    skipped_stocks.append(stock_code)
                    
            except Exception as e:
                logger.error(f"处理股票 {stock_code} 失败: {e}")
                failed_stocks.append(stock_code)
        
        # 输出结果
        logger.info("\n" + "=" * 70)
        logger.info("刷新完成！")
        logger.info(f"总股票数: {len(stocks)}")
        logger.info(f"成功更新: {success_count} 只股票")
        logger.info(f"跳过: {len(skipped_stocks)} 只（无数据或无需更新）")
        logger.info(f"失败: {len(failed_stocks)} 只")
        logger.info(f"成交量类型更新记录数: {total_volume_updated}")
        logger.info(f"K线组合更新记录数: {total_pattern_updated}")
        logger.info(f"总更新记录数: {total_volume_updated + total_pattern_updated}")
        
        if failed_stocks and len(failed_stocks) <= 20:
            logger.warning(f"失败的股票: {', '.join(failed_stocks)}")
        elif failed_stocks:
            logger.warning(f"失败的股票（前20只）: {', '.join(failed_stocks[:20])}...")
        
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"执行过程中出错: {e}", exc_info=True)
    finally:
        conn.close()
        logger.info("数据库连接已关闭")


def main():
    """主函数：支持直接运行或定时任务"""
    import argparse
    
    parser = argparse.ArgumentParser(description='刷新生产库 b_daily_chance 表的数据')
    parser.add_argument('--test', type=int, default=0, help='测试模式，只处理前N只股票')
    parser.add_argument('--days', type=int, default=90, help='刷新最近N天的数据，默认90天（3个月）')
    parser.add_argument('--scheduler', action='store_true', help='启动定时任务模式（每天17:00执行）')
    args = parser.parse_args()
    
    if args.scheduler:
        # 定时任务模式
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.error("=" * 70)
            logger.error("❌ 错误: APScheduler 未安装")
            logger.error("=" * 70)
            logger.error("请运行以下命令安装:")
            logger.error("  pip install APScheduler")
            logger.error("  或")
            logger.error("  pip3 install APScheduler")
            logger.error("=" * 70)
            sys.exit(1)
        
        logger.info("=" * 70)
        logger.info("启动定时任务模式")
        logger.info("定时任务配置: 每天 17:00 执行")
        logger.info("=" * 70)
        
        scheduler = BlockingScheduler()
        
        # 添加定时任务：每天17:00执行
        scheduler.add_job(
            lambda: refresh_job(test_limit=0, days=90),  # 定时任务使用默认参数
            trigger=CronTrigger(hour=17, minute=0),
            id='refresh_volume_and_patterns',
            name='刷新成交量类型和K线组合',
            replace_existing=True
        )
        
        try:
            logger.info("✅ 定时任务已启动，等待执行...")
            # 立即执行一次（可选）
            # refresh_job()
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("⛔ 定时任务已停止")
            scheduler.shutdown()
    else:
        # 直接执行模式
        refresh_job(test_limit=args.test, days=args.days)


if __name__ == '__main__':
    main()

