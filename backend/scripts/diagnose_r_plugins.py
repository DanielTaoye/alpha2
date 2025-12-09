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

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pymysql
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from domain.services.r_point_plugin_service import RPointPluginService

logger = get_logger(__name__)


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
    
    # 判断主板还是非主板
    is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003'))
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
        cond3 = A == 0
        cond4 = C_shadow < 2 * B
        print(f"  [高开低走] 振幅>{amplitude_threshold}%:{cond1}, 阴线:{cond2}, A==0:{cond3}, C<2B:{cond4}")
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
        
        # 8. 阴线跌幅>3%
        if not is_bullish and O > 0:
            change_pct = ((C - O) / O) * 100
            cond1 = change_pct < -3
            print(f"  [阴线跌幅>3%] 阴线:True, 跌幅<-3%:{cond1}(实际{change_pct:.2f}%)")
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
    if len(historical_data) < 5:
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
        
        # 条件2: 前3日涨幅
        if len(historical_data) >= 3:
            prev_3_close = historical_data[2]['close']
            if prev_3_close > 0:
                gain_3days = (current_close - prev_3_close) / prev_3_close * 100
                threshold_3 = 15 if is_main_board else 20
                print(f"  前3日涨幅: {gain_3days:.2f}% (阈值: >{threshold_3}%)")
        
        # 条件3: 前5日涨幅
        if len(historical_data) >= 5:
            prev_5_close = historical_data[4]['close']
            if prev_5_close > 0:
                gain_5days = (current_close - prev_5_close) / prev_5_close * 100
                threshold_5 = 20 if is_main_board else 25
                print(f"  前5日涨幅: {gain_5days:.2f}% (阈值: >{threshold_5}%)")
        
        # 条件5/6: 前15日/20日涨幅
        if len(historical_data) >= 15:
            prev_15_close = historical_data[14]['close']
            if prev_15_close > 0:
                gain_15days = (current_close - prev_15_close) / prev_15_close * 100
                print(f"  前15日涨幅: {gain_15days:.2f}% (条件5需>50%)")
        
        if len(historical_data) >= 20:
            prev_20_close = historical_data[19]['close']
            if prev_20_close > 0:
                gain_20days = (current_close - prev_20_close) / prev_20_close * 100
                print(f"  前20日涨幅: {gain_20days:.2f}% (条件6需>50%)")


def diagnose_pressure_stagnation(stock_code: str, date_str: str, current_data: Dict,
                                  current_chance: Dict, prev_chance: Dict):
    """诊断临近压力位滞涨插件"""
    print("\n" + "=" * 80)
    print("📊 插件2: 临近压力位滞涨")
    print("=" * 80)
    
    if not prev_chance:
        print("  ❌ 无前一日daily_chance数据，无法判断")
        return
    
    # 获取股性
    stock_nature = current_chance.get('stock_nature', '波段') if current_chance else '波段'
    print(f"  股性: {stock_nature}")
    
    # 赔率阈值
    thresholds = {"短线": 12.0, "波段": 10.0, "中长线": 8.0}
    threshold = thresholds.get(stock_nature, 10.0)
    
    # 前一日赔率得分
    day_win_ratio_score = prev_chance.get('day_win_ratio_score', 0) or 0
    print(f"  前一日赔率得分: {day_win_ratio_score:.2f} (需要: 0 < 赔率 < {threshold})")
    
    is_near_pressure = 0 < day_win_ratio_score < threshold
    print(f"  是否满足赔率条件: {'✅' if is_near_pressure else '❌'}")
    
    # 压力位距离
    pressure_price_raw = prev_chance.get('pressure_price', 0) or 0
    if pressure_price_raw > 0:
        pressure_price = pressure_price_raw / 100.0
        current_close = current_data['close']
        distance_pct = (pressure_price - current_close) / current_close * 100
        print(f"  压力位: {pressure_price:.2f}元 (数据库原值: {pressure_price_raw})")
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


def diagnose_fundamental_negative(stock_code: str, date_str: str, current_data: Dict):
    """诊断基本面突发利空插件"""
    print("\n" + "=" * 80)
    print("📊 插件3: 基本面突发利空")
    print("=" * 80)
    
    is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003'))
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


def diagnose_weak_breakout(stock_code: str, date_str: str, current_data: Dict,
                           current_chance: Dict, prev_chance: Dict, historical_data: List[Dict],
                           last_c_point_date: str = None):
    """诊断上冲乏力插件"""
    print("\n" + "=" * 80)
    print("📊 插件4: 上冲乏力")
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
        
        day_win_ratio_score = prev_chance.get('day_win_ratio_score', 0) or 0
        print(f"  前一日赔率: {day_win_ratio_score:.2f} (需要: 0 < 赔率 < {threshold})")
    
    # 检查前日涨幅
    if historical_data:
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003'))
        yesterday_threshold = 6 if is_main_board else 8
        yesterday = historical_data[0]
        yesterday_change = yesterday.get('change_pct', 0) or 0
        print(f"  前日涨幅: {yesterday_change:.2f}% (需要>{yesterday_threshold}%)")


def diagnose_break_support(stock_code: str, date_str: str, current_data: Dict,
                           current_chance: Dict, prev_chance: Dict):
    """诊断跌破支撑位插件"""
    print("\n" + "=" * 80)
    print("📊 插件5: 跌破支撑位")
    print("=" * 80)
    
    if not prev_chance:
        print("  ❌ 无前一日daily_chance数据")
        return
    
    # 支撑位
    support_price_raw = prev_chance.get('support_price', 0) or 0
    if support_price_raw > 0:
        support_price = support_price_raw / 100.0
        current_close = current_data['close']
        
        print(f"  前日支撑位: {support_price:.2f}元 (数据库原值: {support_price_raw})")
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


def diagnose_stock(stock_info: Dict, date_str: str, c_point_date: str = None):
    """完整诊断一只股票"""
    stock_code = stock_info['code']
    stock_name = stock_info['name']
    
    print("\n" + "=" * 80)
    print(f"🔍 R点插件诊断报告")
    print(f"   股票: {stock_code} {stock_name}")
    print(f"   日期: {date_str}")
    if c_point_date:
        print(f"   C点日期: {c_point_date}")
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
    
    # 运行实际的R点检查
    print("\n" + "=" * 80)
    print("🚀 实际R点插件检查结果")
    print("=" * 80)
    
    try:
        r_plugin_service = RPointPluginService()
        # 初始化缓存
        start_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
        r_plugin_service.init_cache(stock_code, start_date, date_str)
        
        # 检查R点
        c_point_datetime = datetime.strptime(c_point_date, '%Y-%m-%d') if c_point_date else None
        check_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        is_r_point, r_plugins = r_plugin_service.check_r_point(
            stock_code, check_date, c_point_datetime
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
    
    # 逐个插件详细诊断
    diagnose_deviation(stock_code, date_str, current_data, current_chance, historical_data)
    diagnose_pressure_stagnation(stock_code, date_str, current_data, current_chance, prev_chance)
    diagnose_fundamental_negative(stock_code, date_str, current_data)
    diagnose_weak_breakout(stock_code, date_str, current_data, current_chance, prev_chance, 
                           historical_data, c_point_date)
    diagnose_break_support(stock_code, date_str, current_data, current_chance, prev_chance)
    
    print("\n" + "=" * 80)
    print("📝 诊断结论")
    print("=" * 80)
    print("   以上是各个R点插件的详细条件检查。")
    print("   要触发R点，需要满足任意一个插件的全部条件。")
    print("   注意: 插件6(高位发R)、插件7(箱体回踩)、插件8(趋势向下)需要完整K线序列和MA/MACD数据，")
    print("   此简化诊断未包含这些插件的检查。如需完整检查，请通过API接口查询。")


def main():
    parser = argparse.ArgumentParser(description='诊断R点插件触发情况')
    parser.add_argument('stock', help='股票名称或代码，如: 东华软件 或 SZ002065')
    parser.add_argument('date', help='日期，格式: YYYY-MM-DD，如: 2025-02-21')
    parser.add_argument('-c', '--c_point', help='C点日期(可选)，格式: YYYY-MM-DD', default=None)
    
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
    diagnose_stock(stock_info, args.date, args.c_point)


if __name__ == '__main__':
    main()

