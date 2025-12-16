"""
诊断R点插件脚本 - 查看某只股票某天为什么触发/没有触发R点

用法:
    python diagnose_r_plugins.py 东华软件 2025-02-21
    python diagnose_r_plugins.py SZ002065 2025-02-21
"""
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import argparse
import requests
from functools import lru_cache

# 控制台输出强制使用UTF-8，避免 Windows 控制台 emoji/中文报编码错误
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
from infrastructure.logging.logger import get_logger
from domain.services.r_point_plugin_service import RPointPluginService
from domain.services.kline_pattern_service import KLinePatternService
from application.services.cr_point_service import CRPointService
from domain.models.kline import KLineData as DomainKLineData

logger = get_logger(__name__)

# API基础URL
API_BASE_URL = "http://localhost:5000"


def get_cr_points_from_api(stock_code: str, table_name: str, start_date: str = None, end_date: str = None) -> Optional[Dict]:
    """
    通过API获取K线+MA+MACD数据（从 /api/kline_data 获取）
    """
    try:
        payload = {
            "table_name": table_name,
            "period_type": "day"
        }
        response = requests.post(f"{API_BASE_URL}/api/kline_data", json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ API请求失败: HTTP {response.status_code}")
            return None
        
        result = response.json()
        if result.get("code") != 200:
            print(f"❌ API返回错误: {result.get('message')}")
            return None
        
        return result.get("data")
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到API服务器 ({API_BASE_URL})，请确保后端服务已启动")
        return None
    except Exception as e:
        print(f"❌ 获取K线数据失败: {e}")
        return None


def _parse_dt(value):
    """将接口返回的日期/时间转为 datetime"""
    if hasattr(value, "strftime"):
        return value
    if value is None:
        return None
    candidate = str(value).replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    return None


def infer_last_cr_points(stock_code: str, stock_name: str, date_str: str, api_data: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    基于 CR 全量计算推断目标日前最近的有效点类型与最近的C点日期
    返回: (last_c_point_date_str, last_valid_point_type)
    """
    try:
        kline_list = api_data.get('kline_data') or api_data.get('klineData') or []
        if not kline_list:
            return None, None

        # 目标日期转换
        target_dt = _parse_dt(date_str)
        if not target_dt:
            return None, None

        # 转 DomainKLineData
        k_objs = []
        for k in kline_list:
            dt = _parse_dt(k.get('date') or k.get('time'))
            if not dt:
                continue
            k_objs.append(DomainKLineData(
                time=dt,
                open=float(k.get('open', 0) or 0),
                high=float(k.get('high', 0) or 0),
                low=float(k.get('low', 0) or 0),
                close=float(k.get('close', 0) or 0),
                volume=float(k.get('volume', 0) or 0),
                liangbi=float(k.get('liangbi', 0) or 0),
                weibi=float(k.get('weibi', 0) or 0),
            ))

        if not k_objs:
            return None, None

        # 只计算到目标日，避免未来数据干扰
        k_objs = [k for k in k_objs if k.time <= target_dt]
        if not k_objs:
            return None, None

        # 需要 MA/MACD 参与策略2计算（若缺失会自动降级）
        ma_data = api_data.get('ma', {})
        macd_data = api_data.get('macd', {})

        cr_service = CRPointService()
        cr_result = cr_service.analyze_cr_points(
            stock_code,
            stock_name,
            k_objs,
            ma_data=ma_data,
            macd_data=macd_data,
            volume_types=None,
            bullish_patterns=None,
            stock_nature=None
        )

        c_points = cr_result.get('c_points', []) or []
        r_points = cr_result.get('r_points', []) or []

        def _last_before(points, ptype):
            last_dt = None
            for p in points:
                if p.get('pointType') != ptype:
                    continue
                dt = _parse_dt(p.get('triggerDate'))
                if dt and dt <= target_dt and (last_dt is None or dt > last_dt):
                    last_dt = dt
            return last_dt

        last_c_dt = _last_before(c_points, 'C')
        last_r_dt = _last_before(r_points, 'R')

        last_type = None
        last_dt = None
        if last_c_dt and (last_dt is None or last_c_dt > last_dt):
            last_type = 'C'
            last_dt = last_c_dt
        if last_r_dt and (last_dt is None or last_r_dt > last_dt):
            last_type = 'R'
            last_dt = last_r_dt

        last_c_str = last_c_dt.strftime('%Y-%m-%d') if last_c_dt else None
        return last_c_str, last_type
    except Exception as e:
        print(f"⚠️ 推断CR序列失败: {e}")
        return None, None


def search_stock(keyword: str) -> Optional[Dict]:
    """
    根据关键词（股票名称或代码）搜索股票
    """
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 先尝试精确匹配代码
            sql = """
                SELECT code, name, nature
                FROM all_stock
                WHERE code = %s OR name = %s
                LIMIT 1
            """
            cursor.execute(sql, (keyword.upper(), keyword))
            result = cursor.fetchone()
            
            if result:
                return {
                    'code': result['code'],
                    'name': result['name'],
                    'nature': result.get('nature', '波段'),
                    'table_name': f"basic_data_{result['code'].lower()}"
                }
            
            # 尝试模糊匹配名称
            sql = """
                SELECT code, name, nature
                FROM all_stock
                WHERE name LIKE %s
                LIMIT 1
            """
            cursor.execute(sql, (f"%{keyword}%",))
            result = cursor.fetchone()
            
            if result:
                return {
                    'code': result['code'],
                    'name': result['name'],
                    'nature': result.get('nature', '波段'),
                    'table_name': f"basic_data_{result['code'].lower()}"
                }
            
            return None
    except Exception as e:
        print(f"❌ 搜索股票失败: {e}")
        return None


def get_prev_trading_day_close(stock_code: str, date_str: str) -> Tuple[Optional[float], Optional[str]]:
    """
    从K线表获取前一个交易日的收盘价
    返回 (收盘价, 日期)
    """
    try:
        table_name = f"basic_data_{stock_code.lower()}"
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = f"""
                SELECT DATE(shi_jian) as trade_date, shou_pan_jia
                FROM `{table_name}`
                WHERE DATE(shi_jian) < %s AND peroid_type = '1day'
                ORDER BY shi_jian DESC
                LIMIT 1
            """
            cursor.execute(sql, (date_str,))
            result = cursor.fetchone()
            
            if result:
                close_price = float(result['shou_pan_jia'] or 0)
                trade_date = result['trade_date'].strftime('%Y-%m-%d') if result['trade_date'] else None
                return close_price, trade_date
            return None, None
    except Exception as e:
        print(f"❌ 获取前一交易日收盘价失败: {e}")
        return None, None


def get_daily_data(stock_code: str, date_str: str) -> Optional[Dict]:
    """获取指定日期的日K线数据"""
    try:
        table_name = f"basic_data_{stock_code.lower()}"
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = f"""
                SELECT shi_jian, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia, 
                       cheng_jiao_liang
                FROM `{table_name}`
                WHERE DATE(shi_jian) = %s AND peroid_type = '1day'
                LIMIT 1
            """
            cursor.execute(sql, (date_str,))
            result = cursor.fetchone()
            
            if result:
                close_price = float(result['shou_pan_jia'] or 0)
                
                # 获取前一交易日收盘价作为前收价
                prev_close, prev_date = get_prev_trading_day_close(stock_code, date_str)
                pre_close = prev_close if prev_close else 0
                
                # 计算涨跌幅
                change_pct = 0
                if pre_close > 0:
                    change_pct = (close_price - pre_close) / pre_close * 100
                
                return {
                    'date': result['shi_jian'],
                    'open': float(result['kai_pan_jia'] or 0),
                    'close': close_price,
                    'high': float(result['zui_gao_jia'] or 0),
                    'low': float(result['zui_di_jia'] or 0),
                    'volume': float(result['cheng_jiao_liang'] or 0),
                    'pre_close': pre_close,
                    'pre_close_date': prev_date,  # 记录前收价来自哪天
                    'change_pct': change_pct
                }
            return None
    except Exception as e:
        print(f"❌ 获取日K线数据失败: {e}")
        return None


def get_daily_chance(stock_code: str, date_str: str) -> Optional[Dict]:
    """获取指定日期的daily_chance数据（从b_daily_chance表）"""
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = """
                SELECT *
                FROM b_daily_chance
                WHERE stock_code = %s AND DATE(date) = %s
                LIMIT 1
            """
            cursor.execute(sql, (stock_code, date_str))
            result = cursor.fetchone()
            return result
    except Exception as e:
        print(f"❌ 获取daily_chance数据失败: {e}")
        return None


def get_prev_daily_chances(stock_code: str, date_str: str, limit: int = 2) -> List[Dict]:
    """获取目标日期之前的最近N个交易日daily_chance（倒序返回）"""
    try:
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = """
                SELECT *
                FROM b_daily_chance
                WHERE stock_code = %s AND DATE(date) < %s
                ORDER BY DATE(date) DESC
                LIMIT %s
            """
            cursor.execute(sql, (stock_code, date_str, limit))
            return cursor.fetchall() or []
    except Exception as e:
        print(f"❌ 获取历史daily_chance失败: {e}")
        return []


def get_historical_daily_data(stock_code: str, date_str: str, days: int = 25) -> List[Dict]:
    """获取历史日K线数据（从K线表查询前N个交易日）"""
    try:
        table_name = f"basic_data_{stock_code.lower()}"
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = f"""
                SELECT shi_jian, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia, 
                       cheng_jiao_liang
                FROM `{table_name}`
                WHERE DATE(shi_jian) < %s AND peroid_type = '1day'
                ORDER BY shi_jian DESC
                LIMIT {days}
            """
            cursor.execute(sql, (date_str,))
            results = cursor.fetchall()
            
            data_list = []
            prev_close = None
            # 倒序遍历以便计算涨跌幅（从最早到最近）
            results_reversed = list(reversed(results))
            for result in results_reversed:
                close_price = float(result['shou_pan_jia'] or 0)
                change_pct = 0
                if prev_close and prev_close > 0:
                    change_pct = (close_price - prev_close) / prev_close * 100
                
                data_list.append({
                    'date': result['shi_jian'],
                    'open': float(result['kai_pan_jia'] or 0),
                    'close': close_price,
                    'high': float(result['zui_gao_jia'] or 0),
                    'low': float(result['zui_di_jia'] or 0),
                    'volume': float(result['cheng_jiao_liang'] or 0),
                    'pre_close': prev_close or 0,
                    'change_pct': change_pct
                })
                prev_close = close_price
            
            # 反转回来，使最近的日期在前面
            return list(reversed(data_list))
    except Exception as e:
        print(f"❌ 获取历史日K线数据失败: {e}")
        return []


def diagnose_deviation(stock_code: str, date_str: str, current_data: Dict, 
                       current_chance: Dict, historical_data: List[Dict]):
    """诊断乖离率偏离插件"""
    print("\n" + "=" * 80)
    print("📊 插件1: 乖离率偏离")
    print("=" * 80)
    
    # 判断主板还是非主板（统一规则）
    is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
    board_type = "主板" if is_main_board else "非主板(创业板/科创板)"
    print(f"  板块类型: {board_type}")
    
    # 检查成交量类型
    volume_type = current_chance.get('volume_type', '') if current_chance else ''
    print(f"  成交量类型: {volume_type or '无数据'}")
    
    xyz_types = ['X', 'Y', 'Z']
    xyh_types = ['X', 'Y', 'H']
    xyzh_types = ['X', 'Y', 'Z', 'H']
    
    volume_types = [t.strip() for t in volume_type.split(',')] if volume_type else []
    is_volume_xyz = any(t in xyz_types for t in volume_types)
    is_volume_xyh = any(t in xyh_types for t in volume_types)
    is_volume_xyzh = any(t in xyzh_types for t in volume_types)
    
    print(f"  是否放量(XYH): {'✅' if is_volume_xyh else '❌'} (条件1-4需要)")
    print(f"  是否放量(XYZH): {'✅' if is_volume_xyzh else '❌'} (条件5-6需要)")
    
    # 检查空头组合
    bearish_pattern = current_chance.get('bearish_pattern', '') if current_chance else ''
    has_bearish_pattern = len(bearish_pattern.strip()) > 0 if bearish_pattern else False
    print(f"  空头组合: {bearish_pattern or '无'}")
    
    # 检查K线形态
    print("\n  --- K线形态检测 ---")
    O = current_data['open']
    C = current_data['close']
    H = current_data['high']
    L = current_data['low']
    
    # 前收价已在 get_daily_data 中从前一交易日K线获取
    prev_close = current_data['pre_close']
    prev_date = current_data.get('pre_close_date')
    if prev_close and prev_close > 0:
        print(f"  前一交易日({prev_date})收盘价: {prev_close:.2f}元")
    elif historical_data:
        prev_close = historical_data[0]['close']
        print(f"  前收价: {prev_close:.2f}元 (从历史数据获取)")
    
    if prev_close == 0:
        print("  ❌ 无法获取前收价，无法判断K线形态")
    else:
        # 计算振幅
        amplitude = ((H - L) / prev_close) * 100
        amplitude_threshold = 6 if is_main_board else 8
        print(f"  振幅: {amplitude:.2f}% (阈值: {amplitude_threshold}%)")
        
        # 计算ABC
        A = H - max(O, C)  # 上影线
        B = abs(C - O)      # 实体
        C_shadow = min(O, C) - L  # 下影线
        
        print(f"  上影线(A): {A:.4f}, 实体(B): {B:.4f}, 下影线(C): {C_shadow:.4f}")
        
        # 检查各种空头K线形态
        is_bullish = O < C
        print(f"  K线类型: {'阳线' if is_bullish else '阴线'}")
        
        matched_patterns = []
        
        # 高振幅阈值（用于十字星）
        high_amp_threshold = 8 if is_main_board else 10
        
        print(f"\n  --- 逐个K线形态检查 ---")
        
        # 1. 冲高回落阳线
        if L > 0:
            b_ratio = (B / L) * 100
            cond1 = amplitude > amplitude_threshold
            cond2 = A >= 2 * C_shadow
            cond3 = A >= 2 * B
            cond4 = 1 < b_ratio < 3.3
            cond5 = is_bullish
            print(f"  [冲高回落阳线] 振幅>{amplitude_threshold}%:{cond1}, A>=2C:{cond2}, A>=2B:{cond3}, 1%<B/L<3.3%:{cond4}(实际{b_ratio:.2f}%), 阳线:{cond5}")
            if cond1 and cond2 and cond3 and cond4 and cond5:
                matched_patterns.append("冲高回落阳线")
                print(f"     ✅ 命中!")
        
        # 2. 冲高回落阴线
        if L > 0:
            b_ratio = (B / L) * 100
            cond1 = amplitude > amplitude_threshold
            cond2 = A >= 2 * C_shadow
            cond3 = A >= 2 * B
            cond4 = 1 < b_ratio < 3.3
            cond5 = not is_bullish
            print(f"  [冲高回落阴线] 振幅>{amplitude_threshold}%:{cond1}, A>=2C:{cond2}, A>=2B:{cond3}, 1%<B/L<3.3%:{cond4}(实际{b_ratio:.2f}%), 阴线:{cond5}")
            if cond1 and cond2 and cond3 and cond4 and cond5:
                matched_patterns.append("冲高回落阴线")
                print(f"     ✅ 命中!")
        
        # 3. 冲高回落阳十字星
        if L > 0 and C_shadow > 0:
            b_ratio = (B / L) * 100
            cond1 = amplitude > amplitude_threshold
            cond2 = is_bullish
            cond3 = b_ratio < 2
            cond4 = A > 2 * C_shadow
            print(f"  [冲高回落阳十字星] 振幅>{amplitude_threshold}%:{cond1}, 阳线:{cond2}, B/L<2%:{cond3}(实际{b_ratio:.2f}%), A>2C:{cond4}")
            if cond1 and cond2 and cond3 and cond4:
                matched_patterns.append("冲高回落阳十字星")
                print(f"     ✅ 命中!")
        
        # 4. 冲高回落阴十字星
        if L > 0 and C_shadow > 0:
            b_ratio = (B / L) * 100
            cond1 = amplitude > amplitude_threshold
            cond2 = not is_bullish
            cond3 = b_ratio < 2
            cond4 = A > 2 * C_shadow
            print(f"  [冲高回落阴十字星] 振幅>{amplitude_threshold}%:{cond1}, 阴线:{cond2}, B/L<2%:{cond3}(实际{b_ratio:.2f}%), A>2C:{cond4}")
            if cond1 and cond2 and cond3 and cond4:
                matched_patterns.append("冲高回落阴十字星")
                print(f"     ✅ 命中!")
        
        # 5. 高开低走
        cond1 = amplitude > amplitude_threshold
        cond2 = not is_bullish
        cond3_a = A == 0
        cond3_b = A < 3 * B
        cond4 = C_shadow < 2 * B
        cond3 = cond3_a or cond3_b
        print(f"  [高开低走] 振幅>{amplitude_threshold}%:{cond1}, 阴线:{cond2}, A==0:{cond3_a}, A<3B:{cond3_b}, C<2B:{cond4}")
        if cond1 and cond2 and cond3 and cond4:
            matched_patterns.append("高开低走")
            print(f"     ✅ 命中!")
        
        # 6. 高振幅阳十字星 (需要更高振幅阈值)
        cond1 = amplitude > high_amp_threshold
        cond2 = A > C_shadow  # 上影线 > 下影线
        cond3 = A > 3 * B     # 上影线 > 3倍实体
        cond4 = C_shadow > 2 * B  # 下影线 > 2倍实体
        cond5 = is_bullish
        print(f"  [高振幅阳十字星] 振幅>{high_amp_threshold}%:{cond1}(实际{amplitude:.2f}%), A>C:{cond2}({A:.4f}>{C_shadow:.4f}), A>3B:{cond3}({A:.4f}>{3*B:.4f}), C>2B:{cond4}({C_shadow:.4f}>{2*B:.4f}), 阳线:{cond5}")
        if cond1 and cond2 and cond3 and cond4 and cond5:
            matched_patterns.append("高振幅阳十字星")
            print(f"     ✅ 命中!")
        
        # 7. 高振幅阴十字星 (需要更高振幅阈值)
        cond1 = amplitude > high_amp_threshold
        cond2 = A > C_shadow  # 上影线 > 下影线
        cond3 = A > 3 * B     # 上影线 > 3倍实体
        cond4 = C_shadow > 2 * B  # 下影线 > 2倍实体
        cond5 = not is_bullish
        print(f"  [高振幅阴十字星] 振幅>{high_amp_threshold}%:{cond1}(实际{amplitude:.2f}%), A>C:{cond2}, A>3B:{cond3}, C>2B:{cond4}, 阴线:{cond5}")
        if cond1 and cond2 and cond3 and cond4 and cond5:
            matched_patterns.append("高振幅阴十字星")
            print(f"     ✅ 命中!")
        
        # 8. 阴线跌幅>3%/5%（主板3%，非主板5%）
        if not is_bullish and O > 0:
            change_pct = ((C - O) / O) * 100
            bearish_threshold = -3 if is_main_board else -5
            cond1 = change_pct < bearish_threshold
            print(f"  [阴线跌幅>{abs(bearish_threshold)}%] 阴线:True, 跌幅<{bearish_threshold}%:{cond1}(实际{change_pct:.2f}%)")
            if cond1:
                matched_patterns.append(f"阴线跌幅{change_pct:.2f}%")
                print(f"     ✅ 命中!")
        
        print(f"\n  --- K线形态检测结果 ---")
        if matched_patterns:
            print(f"  ✅ 命中空头K线形态: {', '.join(matched_patterns)}")
        else:
            print(f"  ❌ 未命中任何空头K线形态")
    
    # 检查历史涨幅
    print("\n  --- 历史涨幅检测 ---")
    if len(historical_data) < 6:
        print(f"  ❌ 历史数据不足(仅{len(historical_data)}天)")
    else:
        current_close = current_data['close']
        
        # 条件1: 连续涨停
        limit_threshold = 9.9 if is_main_board else 19.8
        consecutive_limits = 0
        for i, hist in enumerate(historical_data[:5]):
            if hist['pre_close'] and hist['pre_close'] > 0:
                pct = (hist['close'] - hist['pre_close']) / hist['pre_close'] * 100
                if pct >= limit_threshold:
                    consecutive_limits += 1
                else:
                    break
        print(f"  连续涨停天数: {consecutive_limits} (条件1需>=2)")
        
        # 条件2: 前3日涨幅（起止收盘比，取往前第4个交易日）
        if len(historical_data) >= 4:
            prev_3_close = historical_data[3]['close']
            if prev_3_close and prev_3_close > 0:
                gain_3days = (current_close - prev_3_close) / prev_3_close * 100
                threshold_3 = 15 if is_main_board else 20
                print(f"  前3日涨幅: {gain_3days:.2f}% (阈值: >{threshold_3}%)")
        
        # 条件3: 前5日涨幅（起止收盘比，取往前第6个交易日）
        if len(historical_data) >= 6:
            prev_5_close = historical_data[5]['close']
            if prev_5_close and prev_5_close > 0:
                gain_5days = (current_close - prev_5_close) / prev_5_close * 100
                threshold_5 = 20 if is_main_board else 25
                print(f"  前5日涨幅: {gain_5days:.2f}% (阈值: >{threshold_5}%)")
        
        # 条件5/6: 前15日/20日涨幅（起止收盘比）
        if len(historical_data) >= 16:
            prev_15_close = historical_data[15]['close']
            if prev_15_close and prev_15_close > 0:
                gain_15days = (current_close - prev_15_close) / prev_15_close * 100
                print(f"  前15日涨幅: {gain_15days:.2f}% (条件5需>50%)")
        
        if len(historical_data) >= 21:
            prev_20_close = historical_data[20]['close']
            if prev_20_close and prev_20_close > 0:
                gain_20days = (current_close - prev_20_close) / prev_20_close * 100
                print(f"  前20日涨幅: {gain_20days:.2f}% (条件6需>50%)")


def diagnose_pressure_stagnation(stock_code: str, date_str: str, current_data: Dict,
                                  current_chance: Dict, prev_chance: Dict):
    """诊断临近压力位滞涨插件"""
    print("\n" + "=" * 80)
    print("📊 插件2: 临近压力位滞涨")
    print("=" * 80)
    
    # 补充：打印上一个C点位置（若有）
    if current_chance and current_chance.get('last_c_point'):
        last_c = current_chance.get('last_c_point')
        print(f"  上一个C点: {last_c}")
    elif current_chance and current_chance.get('last_c_point_date'):
        print(f"  上一个C点日期: {current_chance.get('last_c_point_date')}")
    
    if not prev_chance:
        print("  ❌ 无前一日daily_chance数据，无法判断")
        return
    
    # 获取股性
    stock_nature = current_chance.get('stock_nature', '波段') if current_chance else '波段'
    print(f"  股性: {stock_nature}")
    
    # 前一日赔率得分
    day_win_ratio_score = float(prev_chance.get('day_win_ratio_score') or 0)
    print(f"  前一日赔率得分: {day_win_ratio_score:.2f} (需要: 赔率 > 0)")
    
    is_near_pressure = day_win_ratio_score > 0
    print(f"  是否满足赔率条件: {'✅' if is_near_pressure else '❌'}")
    
    # 压力位距离
    pressure_price_raw = float(prev_chance.get('pressure_price') or 0)
    if pressure_price_raw > 0:
        pressure_price = pressure_price_raw / 100.0
        current_close = current_data['close']
        distance_pct = (pressure_price - current_close) / current_close * 100
        print(f"  压力位: {pressure_price:.2f}元 (数据库原值: {pressure_price_raw:.0f})")
        print(f"  当前收盘价: {current_close:.2f}元")
        print(f"  距离压力位: {distance_pct:.2f}% (需要: 0% < 距离 < 10%)")
        
        in_range = 0 < distance_pct < 10
        print(f"  是否在距离范围内: {'✅' if in_range else '❌'}")
    else:
        print("  ❌ 无压力位数据")
    
    # 成交量
    volume_type = current_chance.get('volume_type', '') if current_chance else ''
    xyzh_types = ['X', 'Y', 'Z', 'H']
    volume_types = [t.strip() for t in volume_type.split(',')] if volume_type else []
    is_volume_xyzh = any(t in xyzh_types for t in volume_types)
    print(f"  成交量类型: {volume_type or '无'}")
    print(f"  是否放量(XYZH): {'✅' if is_volume_xyzh else '❌'}")

    # 准备当日风险K线判定
    is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
    amplitude_threshold = 6 if is_main_board else 8
    decline_threshold = 3 if is_main_board else 5

    pattern_today = KLinePatternService.identify_pattern(
        stock_code,
        current_data['open'],
        current_data['close'],
        current_data['high'],
        current_data['low'],
        current_data.get('pre_close', current_data['close'])
    )
    pre_close = current_data.get('pre_close') or current_data['open']
    amplitude_today = (current_data['high'] - current_data['low']) / pre_close * 100 if pre_close else 0
    decline_today = (current_data['close'] - current_data['open']) / current_data['open'] * 100 if current_data['open'] else 0

    risky_set = ["冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", "冲高回落阴十字星", "高开低走"]
    is_risky_amp = pattern_today in risky_set and amplitude_today > amplitude_threshold
    is_risky_decline = (current_data['close'] < current_data['open']) and (decline_today <= -decline_threshold)
    is_risky_today = is_risky_amp or is_risky_decline

    print("\n  --- 情形1：当日放量+风险K线 ---")
    print(f"  当日是否放量(XYZH): {'✅' if is_volume_xyzh else '❌'}")
    print(f"  当日形态: {pattern_today or '无'} | 振幅: {amplitude_today:.2f}% (阈值 {amplitude_threshold}%) | 跌幅: {decline_today:.2f}% (阈值 {-decline_threshold}%)")
    print(f"  风险K线判定: {'✅' if is_risky_today else '❌'}（冲高回落/高开低走且振幅超阈值，或阴线跌幅超阈值）")

    # 情形2：当日未放量，前两日任一天放量 + 当日风险K线（含乌云盖顶）
    print("\n  --- 情形2：前两日放量+风险K线 ---")
    prev_chances = get_prev_daily_chances(stock_code, date_str, 2)
    day1 = prev_chances[0] if len(prev_chances) >= 1 else None
    day2 = prev_chances[1] if len(prev_chances) >= 2 else None

    def _is_volume(chance):
        if not chance:
            return False
        vt = chance.get('volume_type') or ''
        return any(t.strip() in ['X', 'Y', 'Z', 'H'] for t in vt.split(',') if t.strip())

    def _pressure_distance_ok(chance):
        if not chance or not chance.get('pressure_price'):
            return None
        chance_date_raw = chance.get('date')
        chance_date = chance_date_raw.strftime('%Y-%m-%d') if hasattr(chance_date_raw, 'strftime') else str(chance_date_raw)
        day_data = get_daily_data(stock_code, chance_date) if chance_date else None
        if not day_data or not day_data.get('close'):
            return None
        p = float(chance['pressure_price']) / 100.0
        dist = (p - day_data['close']) / day_data['close'] * 100
        return dist, chance_date

    day1_volume = _is_volume(day1)
    day2_volume = _is_volume(day2)
    day1_dist = _pressure_distance_ok(day1) if day1 else None
    day2_dist = _pressure_distance_ok(day2) if day2 else None

    if day1:
        dist_str = f"{day1_dist[0]:.2f}%" if day1_dist else "无数据"
        day1_date = day1_dist[1] if day1_dist and len(day1_dist) > 1 else (day1.get('date').strftime('%Y-%m-%d') if hasattr(day1.get('date'), 'strftime') else day1.get('date'))
        print(f"  前一交易日({day1_date})放量(XYZH): {'✅' if day1_volume else '❌'}，距压: {dist_str}")
    else:
        print("  前一交易日: 无数据")

    if day2:
        dist_str = f"{day2_dist[0]:.2f}%" if day2_dist else "无数据"
        day2_date = day2_dist[1] if day2_dist and len(day2_dist) > 1 else (day2.get('date').strftime('%Y-%m-%d') if hasattr(day2.get('date'), 'strftime') else day2.get('date'))
        print(f"  前两交易日({day2_date})放量(XYZH): {'✅' if day2_volume else '❌'}，距压: {dist_str}")
    else:
        print("  前两交易日: 无数据")
    # 当日风险K线（情形2判定集）
    risk2_set = ["冲高回落阴线", "冲高回落阳线", "高开低走"]
    bearish_combo_today = current_chance.get('bearish_pattern') or ''
    has_cloud = "乌云盖顶" in bearish_combo_today if bearish_combo_today else False
    is_risky_case2 = (pattern_today in risk2_set and amplitude_today > amplitude_threshold) or has_cloud

    print(f"  当日形态: {pattern_today or '无'} | 振幅: {amplitude_today:.2f}% (阈值 {amplitude_threshold}%) | 跌幅: {decline_today:.2f}% (阈值 {-decline_threshold}%)")
    print(f"  空头组合含乌云盖顶: {'✅' if has_cloud else '❌'}")
    print(f"  风险K线判定(情形2): {'✅' if is_risky_case2 else '❌'}（冲高回落/高开低走振幅超阈值 或 乌云盖顶）")


def diagnose_fundamental_negative(stock_code: str, date_str: str, current_data: Dict):
    """诊断基本面突发利空插件"""
    print("\n" + "=" * 80)
    print("📊 插件4: 基本面突发利空")
    print("=" * 80)
    
    is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
    limit_threshold = -9.9 if is_main_board else -19.8
    
    pre_close = current_data['pre_close']
    if pre_close and pre_close > 0:
        change_pct = (current_data['close'] - pre_close) / pre_close * 100
        print(f"  涨跌幅: {change_pct:.2f}% (跌停阈值: {limit_threshold}%)")
        
        if change_pct <= limit_threshold:
            O, H, L, C = current_data['open'], current_data['high'], current_data['low'], current_data['close']
            
            is_one_line = (O == H == L == C)
            is_t_line = (O == L == C and H > C)
            
            print(f"  一字跌停: {'✅' if is_one_line else '❌'}")
            print(f"  T字跌停: {'✅' if is_t_line else '❌'}")
        else:
            print("  ❌ 未达到跌停")
    else:
        print("  ❌ 无前收价数据")


def diagnose_strong_to_weak(stock_code: str, date_str: str,
                            current_data: Dict, current_chance: Dict, prev_chance: Dict):
    """诊断强转弱未反转（插件3）"""
    print("\n" + "=" * 80)
    print("📊 插件3: 强转弱未反转")
    print("=" * 80)
    
    if not prev_chance or not current_chance:
        print("  ❌ 缺少当日或前一日daily_chance数据")
        return
    
    prev_bearish = prev_chance.get('bearish_pattern') or ''
    if "强转弱" not in prev_bearish:
        print("  ❌ 前一日空头组合不含“强转弱”")
        return
    
    # 找到前一交易日日期
    prev_date = prev_chance.get('date')
    if isinstance(prev_date, datetime):
        prev_date = prev_date.strftime('%Y-%m-%d')
    if not prev_date:
        prev_date = current_data.get('pre_close_date')
    if not prev_date:
        print("  ❌ 未找到前一交易日日期，无法获取K线")
        return
    
    prev_daily = get_daily_data(stock_code, prev_date)
    if not prev_daily:
        print(f"  ❌ 未获取到前一日({prev_date})K线数据")
        return
    
    mid_prev = (prev_daily['close'] + prev_daily['open']) / 2
    today_close = current_data['close']
    print(f"  前一日中位价(收+开)/2: {mid_prev:.2f}，今日收盘: {today_close:.2f}")
    repaired = today_close >= mid_prev
    print(f"  是否已修复(今日收盘>=中位): {'✅' if repaired else '❌'}")
    
    vol_today = current_chance.get('volume_type') or ''
    vols = [v.strip() for v in vol_today.split(',') if v.strip()]
    has_g = "G" in vols
    print(f"  今日成交量类型: {vol_today or '无'} (需要含 G): {'✅' if has_g else '❌'}")
    
    if (not repaired) and has_g:
        print("  ✅ 触发强转弱未反转")
    else:
        print("  ❌ 未触发强转弱未反转")


def diagnose_weak_breakout(stock_code: str, date_str: str, current_data: Dict,
                           current_chance: Dict, prev_chance: Dict, historical_data: List[Dict],
                           last_c_point_date: str = None):
    """诊断上冲乏力插件"""
    print("\n" + "=" * 80)
    print("📊 插件5: 上冲乏力")
    print("=" * 80)
    
    if not last_c_point_date:
        print("  ⚠️ 未提供C点日期，无法判断上冲乏力条件")
        print("  (需要有前置C点才能触发此插件)")
        return
    
    # 获取C点数据
    c_data = get_daily_data(stock_code, last_c_point_date)
    if not c_data:
        print(f"  ❌ 无法获取C点({last_c_point_date})数据")
        return
    
    # 计算累计涨幅
    cumulative_gain = (current_data['close'] - c_data['close']) / c_data['close'] * 100 if c_data['close'] else 0
    print(f"  C点日期: {last_c_point_date}")
    print(f"  C点收盘价: {c_data['close']:.2f}元")
    print(f"  当前收盘价: {current_data['close']:.2f}元")
    print(f"  从C点涨幅: {cumulative_gain:.2f}% (需要>15%)")
    
    if cumulative_gain <= 15:
        print("  ❌ 涨幅不足15%")
        return
    
    # 检查赔率
    if prev_chance:
        stock_nature = current_chance.get('stock_nature', '波段') if current_chance else '波段'
        thresholds = {"短线": 15.0, "波段": 12.0, "中长线": 10.0}
        threshold = thresholds.get(stock_nature, 12.0)
        
        day_win_ratio_score = float(prev_chance.get('day_win_ratio_score') or 0)
        print(f"  前一日赔率: {day_win_ratio_score:.2f} (需要: 0 < 赔率 < {threshold})")
    
    # 检查前日涨幅
    if historical_data:
        is_main_board = KLinePatternService.is_main_board(stock_code) if stock_code else True
        yesterday_threshold = 6 if is_main_board else 8
        yesterday = historical_data[0]
        yesterday_change = yesterday.get('change_pct', 0) or 0
        print(f"  前日涨幅: {yesterday_change:.2f}% (需要>{yesterday_threshold}%)")


def diagnose_break_support(stock_code: str, date_str: str, current_data: Dict,
                           current_chance: Dict, prev_chance: Dict):
    """诊断跌破支撑位插件"""
    print("\n" + "=" * 80)
    print("📊 插件6: 跌破支撑位")
    print("=" * 80)
    
    if not prev_chance:
        print("  ❌ 无前一日daily_chance数据")
        return
    
    # 支撑位
    support_price_raw = float(prev_chance.get('support_price') or 0)
    if support_price_raw > 0:
        support_price = support_price_raw / 100.0
        current_close = current_data['close']
        
        print(f"  前日支撑位: {support_price:.2f}元 (数据库原值: {support_price_raw:.0f})")
        print(f"  当前收盘价: {current_close:.2f}元")
        
        is_break = current_close < support_price
        print(f"  是否跌破支撑: {'✅' if is_break else '❌'}")
        
        # 成交量
        volume_type = current_chance.get('volume_type', '') if current_chance else ''
        xyz_types = ['X', 'Y', 'Z']
        volume_types = [t.strip() for t in volume_type.split(',')] if volume_type else []
        is_volume_xyz = any(t in xyz_types for t in volume_types)
        print(f"  成交量类型: {volume_type or '无'}")
        print(f"  是否放量(XYZ): {'✅' if is_volume_xyz else '❌'} (此插件需要放量)")
    else:
        print("  ❌ 无支撑位数据")


def diagnose_high_position_r(stock_code: str, date_str: str, current_data: Dict,
                              prev_chance: Dict, ma_data: Dict, macd_data: Dict,
                              kline_list: List, target_index: int):
    """诊断高位发R插件（插件7）"""
    print("\n" + "=" * 80)
    print("📊 插件7: 高位发R")
    print("=" * 80)
    
    if not ma_data or not macd_data:
        print("  ❌ 缺少MA或MACD数据，无法诊断")
        return
    
    if target_index < 0:
        print("  ❌ 未找到目标日期的K线索引")
        return
    
    current_price = current_data['close']
    
    # 条件1: 均线多头排列
    print("\n  --- 条件1: 均线多头排列 ---")
    ma5 = ma_data.get('ma5', [])[target_index] if target_index < len(ma_data.get('ma5', [])) else None
    ma10 = ma_data.get('ma10', [])[target_index] if target_index < len(ma_data.get('ma10', [])) else None
    ma20 = ma_data.get('ma20', [])[target_index] if target_index < len(ma_data.get('ma20', [])) else None
    ma30 = ma_data.get('ma30', [])[target_index] if target_index < len(ma_data.get('ma30', [])) else None
    ma60 = ma_data.get('ma60', [])[target_index] if target_index < len(ma_data.get('ma60', [])) else None
    
    if None in [ma5, ma10, ma20, ma30, ma60]:
        print(f"  均线数据不完整: MA5={ma5}, MA10={ma10}, MA20={ma20}, MA30={ma30}, MA60={ma60}")
    else:
        is_bullish_alignment = ma5 > ma10 > ma20 > ma30 > ma60
        print(f"  MA5={ma5:.2f} > MA10={ma10:.2f} > MA20={ma20:.2f} > MA30={ma30:.2f} > MA60={ma60:.2f}")
        print(f"  当前多头排列: {'✅' if is_bullish_alignment else '❌'}")
        
        # 检查前3日是否有多头排列
        for i in range(1, 4):
            check_idx = target_index - i
            if check_idx >= 0:
                m5 = ma_data.get('ma5', [])[check_idx] if check_idx < len(ma_data.get('ma5', [])) else None
                m10 = ma_data.get('ma10', [])[check_idx] if check_idx < len(ma_data.get('ma10', [])) else None
                m20 = ma_data.get('ma20', [])[check_idx] if check_idx < len(ma_data.get('ma20', [])) else None
                m30 = ma_data.get('ma30', [])[check_idx] if check_idx < len(ma_data.get('ma30', [])) else None
                m60 = ma_data.get('ma60', [])[check_idx] if check_idx < len(ma_data.get('ma60', [])) else None
                if None not in [m5, m10, m20, m30, m60]:
                    was_bullish = m5 > m10 > m20 > m30 > m60
                    print(f"  前{i}日多头排列: {'✅' if was_bullish else '❌'}")
    
    # 条件2: 20日最低价涨幅>18%
    print("\n  --- 条件2: 20日涨幅 ---")
    if target_index >= 20 and len(kline_list) > target_index:
        lowest_price = min(k.get('low', float('inf')) for k in kline_list[target_index-20:target_index])
        gain_from_lowest = (current_price - lowest_price) / lowest_price * 100 if lowest_price > 0 else 0
        print(f"  20日最低价: {lowest_price:.2f}, 当前价: {current_price:.2f}")
        print(f"  涨幅: {gain_from_lowest:.2f}% (需要>18%): {'✅' if gain_from_lowest > 18 else '❌'}")
    else:
        print("  ❌ 数据不足20天")
    
    # 条件3: 股价>MA10
    print("\n  --- 条件3: 股价>MA10 ---")
    if ma10:
        print(f"  股价{current_price:.2f} > MA10({ma10:.2f}): {'✅' if current_price > ma10 else '❌'}")
    
    # 条件4: 跌破支撑位
    print("\n  --- 条件4: 跌破支撑位 ---")
    if prev_chance:
        support_raw = float(prev_chance.get('support_price') or 0)
        if support_raw > 0:
            support_price = support_raw / 100.0
            is_break = current_price < support_price
            print(f"  支撑位: {support_price:.2f}, 当前价: {current_price:.2f}")
            print(f"  是否跌破: {'✅' if is_break else '❌'}")
        else:
            print("  ❌ 无支撑位数据")
    else:
        print("  ❌ 无前一日数据")
    
    # 条件5: MACD死叉
    print("\n  --- 条件5: MACD死叉 ---")
    dif_list = macd_data.get('dif', [])
    dea_list = macd_data.get('dea', [])
    if dif_list and dea_list and target_index < len(dif_list):
        curr_dif = dif_list[target_index]
        curr_dea = dea_list[target_index]
        print(f"  当前 DIF={curr_dif:.4f}, DEA={curr_dea:.4f}")
        print(f"  DIF < DEA (死叉状态): {'✅' if curr_dif < curr_dea else '❌'}")
        
        # 检查前5日是否有死叉转换
        for i in range(1, 6):
            check_idx = target_index - i
            if check_idx >= 1:
                prev_dif = dif_list[check_idx - 1]
                prev_dea = dea_list[check_idx - 1]
                curr_d = dif_list[check_idx]
                curr_e = dea_list[check_idx]
                if prev_dif > prev_dea and curr_d < curr_e:
                    print(f"  前{i}日出现死叉转换点 ✅")
                    break
    else:
        print("  ❌ MACD数据不足")


def diagnose_box_breakdown(stock_code: str, date_str: str, current_data: Dict,
                           prev_chance: Dict, macd_data: Dict, kline_list: List, target_index: int):
    """诊断箱体回踩被跌破插件（插件8）"""
    print("\n" + "=" * 80)
    print("📊 插件8: 箱体回踩被跌破")
    print("=" * 80)
    
    if target_index < 42:
        print(f"  ❌ 数据不足42天（当前索引: {target_index}）")
        return
    
    current_price = current_data['close']
    
    # 步骤1: 找X日（今天往前20天的最高价所在日）
    print("\n  --- 步骤1: 找X日（前20天最高价）---")
    x_day_high = 0
    x_day_index = -1
    for i in range(target_index - 19, target_index + 1):
        if i >= 0 and i < len(kline_list):
            if kline_list[i].get('high', 0) > x_day_high:
                x_day_high = kline_list[i].get('high', 0)
                x_day_index = i
    
    if x_day_index >= 0:
        x_date = kline_list[x_day_index].get('date', '')
        print(f"  X日: {x_date}, 最高价: {x_day_high:.2f}")
        
        # 检查回落幅度
        drop_ratio = (x_day_high - current_price) / x_day_high * 100 if x_day_high > 0 else 0
        print(f"  当前价{current_price:.2f}较X日回落: {drop_ratio:.2f}% (需要>20%): {'✅' if drop_ratio > 20 else '❌'}")
    else:
        print("  ❌ 无法找到X日")
        return
    
    # 步骤2: 从X日往前22天找Y日和Z日
    print("\n  --- 步骤2: 找Y日和Z日 ---")
    if x_day_index >= 22:
        box_start = x_day_index - 22
        box_end = x_day_index - 1
        
        # 找Y日
        y_day_high = None
        for i in range(box_start, box_end + 1):
            if kline_list[i].get('high', 0) > x_day_high:
                if y_day_high is None or kline_list[i].get('high', 0) > y_day_high:
                    y_day_high = kline_list[i].get('high', 0)
        
        # 找Z日
        z_day_low = float('inf')
        for i in range(box_start, box_end + 1):
            if kline_list[i].get('low', float('inf')) < z_day_low:
                z_day_low = kline_list[i].get('low', float('inf'))
        
        if y_day_high:
            print(f"  Y日最高价: {y_day_high:.2f} (比X日更高)")
            box_gain = (y_day_high - z_day_low) / z_day_low * 100 if z_day_low > 0 else 0
            print(f"  Z日最低价: {z_day_low:.2f}")
            print(f"  Y-Z涨幅: {box_gain:.2f}% (需要>20%): {'✅' if box_gain > 20 else '❌'}")
        else:
            print(f"  无Y日（X日前22天没有更高价）")
            box_gain = (x_day_high - z_day_low) / z_day_low * 100 if z_day_low > 0 else 0
            print(f"  Z日最低价: {z_day_low:.2f}")
            print(f"  X-Z涨幅: {box_gain:.2f}% (需要>20%): {'✅' if box_gain > 20 else '❌'}")
    
    # 步骤3: 跌破支撑位
    print("\n  --- 步骤3: 跌破支撑位 ---")
    if prev_chance:
        support_raw = float(prev_chance.get('support_price') or 0)
        if support_raw > 0:
            support_price = support_raw / 100.0
            is_break = current_price < support_price
            print(f"  支撑位: {support_price:.2f}, 当前价: {current_price:.2f}")
            print(f"  是否跌破: {'✅' if is_break else '❌'}")
    
    # 步骤4: MACD死叉
    print("\n  --- 步骤4: MACD死叉 ---")
    dif_list = macd_data.get('dif', [])
    dea_list = macd_data.get('dea', [])
    if dif_list and dea_list and target_index < len(dif_list):
        for i in range(max(1, target_index - 5), target_index + 1):
            if i > 0:
                prev_dif = dif_list[i - 1]
                prev_dea = dea_list[i - 1]
                curr_dif = dif_list[i]
                curr_dea = dea_list[i]
                if prev_dif > prev_dea and curr_dif < curr_dea:
                    print(f"  索引{i}出现死叉转换 ✅")
                    break
        else:
            print("  前5日未发现死叉转换 ❌")


def diagnose_high_stagnation_bearish(stock_code: str, date_str: str, current_data: Dict,
                                     current_chance: Dict, prev_chance: Dict,
                                     macd_data: Dict, kline_list: List, target_index: int):
    """诊断高位滞涨+空头组合（插件10）"""
    print("\n" + "=" * 80)
    print("📊 插件10: 高位滞涨+空头组合")
    print("=" * 80)
    
    if not current_chance or not prev_chance:
        print("  ❌ 缺少当日或前一日daily_chance数据")
        return
    
    if target_index < 39:
        print(f"  ❌ 数据不足40个交易日（当前索引: {target_index}）")
        return
    
    # 步骤1：近20日最高价X
    x_range_start = max(0, target_index - 19)
    x_range_end = target_index
    x_high = -1
    x_idx = -1
    for i in range(x_range_start, x_range_end + 1):
        h = float(kline_list[i].get('high', 0) or 0)
        if h > x_high:
            x_high = h
            x_idx = i
    if x_idx < 0:
        print("  ❌ 未找到X日")
        return
    x_date = kline_list[x_idx].get('date') or kline_list[x_idx].get('time')
    if hasattr(x_date, 'strftime'):
        x_date = x_date.strftime('%Y-%m-%d')
    
    # 步骤2：X日前20日最低价Y
    if x_idx < 20:
        print("  ❌ X日前数据不足20天")
        return
    y_low = None
    y_date = None
    for i in range(x_idx - 20, x_idx):
        low_v = float(kline_list[i].get('low', 0) or 0)
        if y_low is None or low_v < y_low:
            y_low = low_v
            y_date_raw = kline_list[i].get('date') or kline_list[i].get('time')
            y_date = y_date_raw.strftime('%Y-%m-%d') if hasattr(y_date_raw, 'strftime') else y_date_raw
    if not y_low or y_low <= 0:
        print("  ❌ Y日最低价无效")
        return
    
    gain_high = (x_high - y_low) / y_low * 100
    print(f"  X日({x_date})最高: {x_high:.2f}, Y日({y_date})最低: {y_low:.2f}, 涨幅: {gain_high:.2f}% (需>15%)")
    if gain_high <= 15:
        print("  ❌ 高位涨幅不足15%")
        return
    
    # 步骤3：跌破前一日支撑
    support_raw = float(prev_chance.get('support_price') or 0)
    if support_raw <= 0:
        print("  ❌ 前一日无支撑位数据")
        return
    support_price = support_raw / 100.0
    close_today = current_data['close']
    break_support = close_today < support_price
    print(f"  前日支撑: {support_price:.2f}，今日收盘: {close_today:.2f}，是否跌破: {'✅' if break_support else '❌'}")
    if not break_support:
        return
    
    # 条件A：空头组合 + 跌破支撑
    bearish_pattern = current_chance.get('bearish_pattern') or ''
    has_bearish_combo = len(bearish_pattern.strip()) > 0
    print(f"  当日空头组合: {bearish_pattern or '无'} (需非空): {'✅' if has_bearish_combo else '❌'}")
    if has_bearish_combo:
        print(f"  ✅ 触发: 空头组合+跌破支撑")
        return
    
    # 条件B：MACD死叉（含前5日）+ 跌破支撑
    dif_list = macd_data.get('dif', [])
    dea_list = macd_data.get('dea', [])
    if not dif_list or not dea_list or target_index >= len(dif_list) or target_index < 1:
        print("  ❌ MACD数据不足")
        return
    
    death_cross_found = False
    start_idx = max(1, target_index - 5)
    for i in range(start_idx, target_index + 1):
        prev_d = dif_list[i - 1]
        prev_e = dea_list[i - 1]
        curr_d = dif_list[i]
        curr_e = dea_list[i]
        if None in [prev_d, prev_e, curr_d, curr_e]:
            continue
        if prev_d > prev_e and curr_d < curr_e:
            death_cross_found = True
            print(f"  在索引{i}发现MACD死叉 ✅")
            break
        if i == target_index and curr_d < curr_e:
            death_cross_found = True
            print(f"  当日MACD已在零轴下方死叉 ✅")
            break
    
    if death_cross_found:
        print("  ✅ 触发: MACD死叉+跌破支撑")
    else:
        print("  ❌ 未发现近5日MACD死叉，未触发")


def diagnose_downtrend_break(stock_code: str, date_str: str, current_data: Dict,
                              prev_chance: Dict, ma_data: Dict, macd_data: Dict, target_index: int):
    """诊断趋势向下+跌破支撑+MACD死叉插件（插件9）"""
    print("\n" + "=" * 80)
    print("📊 插件9: 趋势向下+未放量跌破支撑+MACD死叉")
    print("=" * 80)
    
    current_price = current_data['close']
    
    # 条件1: 股价在60日均线下方
    print("\n  --- 条件1: 股价<MA60 ---")
    ma60_list = ma_data.get('ma60', [])
    if ma60_list and target_index < len(ma60_list):
        ma60 = ma60_list[target_index]
        if ma60:
            is_below_ma60 = current_price < ma60
            print(f"  股价{current_price:.2f} < MA60({ma60:.2f}): {'✅' if is_below_ma60 else '❌'}")
        else:
            print("  ❌ MA60数据为空")
    else:
        print("  ❌ MA60数据不足")
    
    # 条件2: 跌破支撑位
    print("\n  --- 条件2: 跌破支撑位 ---")
    if prev_chance:
        support_raw = float(prev_chance.get('support_price') or 0)
        if support_raw > 0:
            support_price = support_raw / 100.0
            is_break = current_price < support_price
            print(f"  支撑位: {support_price:.2f}, 当前价: {current_price:.2f}")
            print(f"  是否跌破: {'✅' if is_break else '❌'}")
        else:
            print("  ❌ 无支撑位数据")
    
    # 条件3: MACD死叉
    print("\n  --- 条件3: MACD死叉 ---")
    dif_list = macd_data.get('dif', [])
    dea_list = macd_data.get('dea', [])
    if dif_list and dea_list and target_index < len(dif_list):
        curr_dif = dif_list[target_index]
        curr_dea = dea_list[target_index]
        print(f"  当前 DIF={curr_dif:.4f}, DEA={curr_dea:.4f}")
        
        # 检查当前及前3日是否有死叉
        for i in range(max(1, target_index - 3), target_index + 1):
            if i > 0:
                prev_dif = dif_list[i - 1]
                prev_dea = dea_list[i - 1]
                curr_d = dif_list[i]
                curr_e = dea_list[i]
                if prev_dif > prev_dea and curr_d < curr_e:
                    print(f"  索引{i}出现死叉转换 ✅")
                    break
        else:
            print("  当前及前3日未发现死叉转换 ❌")


def diagnose_stock(stock_info: Dict, date_str: str, c_point_date: str = None, last_valid_point_type: str = None):
    """完整诊断一只股票"""
    stock_code = stock_info['code']
    stock_name = stock_info['name']
    
    print("\n" + "=" * 80)
    print(f"🔍 R点插件诊断报告")
    print(f"   股票: {stock_code} {stock_name}")
    print(f"   日期: {date_str}")
    if c_point_date:
        print(f"   C点日期: {c_point_date}")
    if last_valid_point_type:
        print(f"   上一有效点类型: {last_valid_point_type}")
    print("=" * 80)
    
    # 获取当日数据
    current_data = get_daily_data(stock_code, date_str)
    if not current_data:
        print(f"❌ 无法获取 {date_str} 的K线数据，可能是非交易日")
        return
    
    prev_close_display = current_data['pre_close']
    prev_date_display = current_data.get('pre_close_date')
    
    print(f"\n📈 当日K线数据:")
    print(f"   开盘: {current_data['open']:.2f}  收盘: {current_data['close']:.2f}")
    print(f"   最高: {current_data['high']:.2f}  最低: {current_data['low']:.2f}")
    if prev_date_display:
        print(f"   前收: {prev_close_display:.2f} (来自{prev_date_display}收盘价)  涨跌幅: {current_data['change_pct']:.2f}%")
    else:
        print(f"   前收: {prev_close_display:.2f}  涨跌幅: {current_data['change_pct']:.2f}%")
    
    # 获取当日daily_chance
    current_chance = get_daily_chance(stock_code, date_str)
    if current_chance:
        print(f"\n📋 当日Daily Chance数据:")
        print(f"   成交量类型: {current_chance.get('volume_type') or '无'}")
        print(f"   空头组合: {current_chance.get('bearish_pattern') or '无'}")
        print(f"   多头组合: {current_chance.get('bullish_pattern') or '无'}")
        day_score = float(current_chance.get('day_win_ratio_score') or 0)
        print(f"   日线赔率分: {day_score:.2f}")
        print(f"   股性: {current_chance.get('stock_nature') or '无'}")
    else:
        print(f"\n⚠️ 无当日Daily Chance数据")
    
    # 获取前一日daily_chance
    prev_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    prev_chance = None
    for i in range(7):  # 尝试找到前一个交易日
        test_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=i+1)).strftime('%Y-%m-%d')
        prev_chance = get_daily_chance(stock_code, test_date)
        if prev_chance:
            print(f"\n📋 前一交易日({test_date}) Daily Chance数据:")
            day_score = float(prev_chance.get('day_win_ratio_score') or 0)
            pressure_raw = float(prev_chance.get('pressure_price') or 0)
            support_raw = float(prev_chance.get('support_price') or 0)
            print(f"   日线赔率分: {day_score:.2f}")
            print(f"   压力位: {pressure_raw / 100.0:.2f}元")
            print(f"   支撑位: {support_raw / 100.0:.2f}元")
            break
    
    # 获取历史数据
    historical_data = get_historical_daily_data(stock_code, date_str, 25)

    # 缓存API数据，避免多次请求
    api_data_cache = {}
    table_name = stock_info.get('table_name', f"basic_data_{stock_code.lower()}")

    @lru_cache(maxsize=1)
    def load_api_data():
        api_start_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
        data = get_cr_points_from_api(stock_code, table_name, api_start_date, date_str)
        if data:
            api_data_cache.update(data)
        return data

    # 如果未显式传入C点/上一有效点，尝试用CR全量计算推断
    inferred_c_point = c_point_date
    inferred_last_type = last_valid_point_type
    api_data_for_infer = load_api_data()
    if api_data_for_infer and (not c_point_date or not last_valid_point_type):
        last_c, last_type = infer_last_cr_points(stock_code, stock_name, date_str, api_data_for_infer)
        if not inferred_c_point:
            inferred_c_point = last_c
        if not inferred_last_type:
            inferred_last_type = last_type
        print("\n🧭 自动推断CR序列(基于CRPointService全量计算):")
        print(f"   最近C点: {last_c or '未找到'}")
        print(f"   上一有效点类型: {last_type or '未找到'}")
    else:
        if inferred_c_point or inferred_last_type:
            print("\n🧭 使用外部传入的CR上下文")
            if inferred_c_point:
                print(f"   最近C点: {inferred_c_point}")
            if inferred_last_type:
                print(f"   上一有效点类型: {inferred_last_type}")
    
    # 运行实际的R点检查（第一遍：仅缓存数据，用于对比）
    print("\n" + "=" * 80)
    print("🚀 实际R点插件检查结果（仅缓存，不含MA/MACD）")
    print("=" * 80)
    
    try:
        r_plugin_service = RPointPluginService()
        # 初始化缓存
        start_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
        r_plugin_service.init_cache(stock_code, start_date, date_str)
        
        # 检查R点（不带MA/MACD，可能导致插件7-10被跳过）
        c_point_datetime = datetime.strptime(inferred_c_point, '%Y-%m-%d') if inferred_c_point else None
        check_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        is_r_point, r_plugins = r_plugin_service.check_r_point(
            stock_code, check_date, c_point_datetime, last_valid_point_type=inferred_last_type
        )
        
        if is_r_point:
            print(f"   ✅ 触发R点!")
            for plugin in r_plugins:
                print(f"   📍 {plugin.plugin_name}: {plugin.reason}")
        else:
            print(f"   ❌ 未触发R点")
            print(f"   (插件返回空列表)")
    except Exception as e:
        print(f"   ⚠️ 检查过程出错: {e}")
    
    # 逐个插件详细诊断（插件1-6）
    diagnose_deviation(stock_code, date_str, current_data, current_chance, historical_data)
    diagnose_pressure_stagnation(stock_code, date_str, current_data, current_chance, prev_chance)
    diagnose_strong_to_weak(stock_code, date_str, current_data, current_chance, prev_chance)
    diagnose_fundamental_negative(stock_code, date_str, current_data)
    diagnose_weak_breakout(stock_code, date_str, current_data, current_chance, prev_chance, 
                           historical_data, c_point_date)
    diagnose_break_support(stock_code, date_str, current_data, current_chance, prev_chance)
    
    # 通过API获取完整数据（MA、MACD、K线序列）用于诊断插件7-10
    print("\n" + "=" * 80)
    print("📡 从API获取MA/MACD数据（用于插件7-10诊断）")
    print("=" * 80)
    
    table_name = stock_info.get('table_name', f"basic_data_{stock_code.lower()}")
    # 获取足够长的历史数据（60天）
    api_start_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
    api_data = api_data_cache or load_api_data()

    if api_data:
        ma_data = api_data.get('ma', {})
        macd_data = api_data.get('macd', {})
        # 后端返回字段名为 kline_data，这里兼容旧字段 klineData
        kline_list = api_data.get('kline_data') or api_data.get('klineData') or []
        
        print(f"   ✅ 获取到 {len(kline_list)} 条K线数据")
        print(f"   MA数据: MA5={len(ma_data.get('ma5', []))}条, MA60={len(ma_data.get('ma60', []))}条")
        print(f"   MACD数据: DIF={len(macd_data.get('dif', []))}条, DEA={len(macd_data.get('dea', []))}条")
        
        # 找到目标日期的索引
        target_index = -1
        for i, kline in enumerate(kline_list):
            # 兼容字段: date 或 time
            kline_date = kline.get('date') or kline.get('time') or ''
            if isinstance(kline_date, str):
                if kline_date.startswith(date_str):
                    target_index = i
                    break
            elif hasattr(kline_date, 'strftime') and kline_date.strftime('%Y-%m-%d') == date_str:
                target_index = i
                break
        
        if target_index >= 0:
            print(f"   目标日期索引: {target_index}")
            
            # ==== 第二遍：携带MA/MACD/索引 重新跑一次check_r_point，确保插件7-10参与 ====
            try:
                from types import SimpleNamespace
                
                def to_dt(v):
                    if hasattr(v, "strftime"):
                        return v
                    try:
                        return datetime.fromisoformat(str(v).replace('T', ' '))
                    except Exception:
                        return None
                
                k_objs = []
                for k in kline_list:
                    k_objs.append(SimpleNamespace(
                        high=float(k.get('high', 0) or 0),
                        low=float(k.get('low', 0) or 0),
                        close=float(k.get('close', 0) or 0),
                        open=float(k.get('open', 0) or 0),
                        time=to_dt(k.get('date') or k.get('time'))
                    ))
                
                r_plugin_service2 = RPointPluginService()
                start_date2 = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
                r_plugin_service2.init_cache(stock_code, start_date2, date_str)
                c_point_datetime = datetime.strptime(inferred_c_point, '%Y-%m-%d') if inferred_c_point else None
                check_date = datetime.strptime(date_str, '%Y-%m-%d')
                
                is_r_point2, r_plugins2 = r_plugin_service2.check_r_point(
                    stock_code, check_date, c_point_datetime,
                    ma_data=ma_data, macd_data=macd_data,
                    current_index=target_index, kline_data=k_objs,
                    last_valid_point_type=inferred_last_type
                )
                
                print("\n🛰 携带MA/MACD/索引的R点重检结果")
                if is_r_point2:
                    print("   ✅ 触发R点!")
                    for plugin in r_plugins2:
                        print(f"   📍 {plugin.plugin_name}: {plugin.reason}")
                else:
                    print("   ❌ 未触发R点（含MA/MACD）")
            except Exception as e:
                print(f"   ⚠️ 携带MA/MACD重检失败: {e}")
            
            # 诊断插件7-10
            diagnose_high_position_r(stock_code, date_str, current_data, prev_chance, 
                                     ma_data, macd_data, kline_list, target_index)
            diagnose_box_breakdown(stock_code, date_str, current_data, prev_chance,
                                   macd_data, kline_list, target_index)
            diagnose_downtrend_break(stock_code, date_str, current_data, prev_chance,
                                     ma_data, macd_data, target_index)
            diagnose_high_stagnation_bearish(stock_code, date_str, current_data, current_chance,
                                             prev_chance, macd_data, kline_list, target_index)
        else:
            print(f"   ❌ 在K线数据中未找到目标日期 {date_str}")
    else:
        print("   ❌ 无法从API获取数据，跳过插件7-10诊断")
        print("   请确保后端服务已启动: python app.py")
    
    print("\n" + "=" * 80)
    print("📝 诊断结论")
    print("=" * 80)
    print("   以上是所有8个R点插件的详细条件检查。")
    print("   要触发R点，需要满足任意一个插件的全部条件。")


def main():
    parser = argparse.ArgumentParser(description='诊断R点插件触发情况')
    parser.add_argument('stock', help='股票名称或代码，如: 东华软件 或 SZ002065')
    parser.add_argument('date', help='日期，格式: YYYY-MM-DD，如: 2025-02-21')
    parser.add_argument('-c', '--c_point', help='C点日期(可选)，格式: YYYY-MM-DD', default=None)
    parser.add_argument('-p', '--prev_point_type', help='上一有效点类型，可选: R 或 C', default=None)
    
    args = parser.parse_args()
    
    # 搜索股票
    print(f"🔍 搜索股票: {args.stock}")
    stock_info = search_stock(args.stock)
    
    if not stock_info:
        print(f"❌ 未找到股票: {args.stock}")
        print("   请检查股票名称或代码是否正确")
        return
    
    print(f"✅ 找到股票: {stock_info['code']} {stock_info['name']} ({stock_info['nature']})")
    
    # 验证日期格式
    try:
        datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        print(f"❌ 日期格式错误: {args.date}")
        print("   正确格式: YYYY-MM-DD，如: 2025-02-21")
        return
    
    # 诊断
    diagnose_stock(stock_info, args.date, args.c_point, args.prev_point_type)


if __name__ == '__main__':
    main()

