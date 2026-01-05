"""回测服务"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
import functools
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
import pymysql
from domain.services.trading_calendar_service import TradingCalendarService
import pandas as pd

logger = get_logger(__name__)


class BacktestService:
    """回测服务 - 计算C点买入R点卖出的收益率"""
    
    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def _check_1day_data_cached(table_name: str) -> bool:
        """
        检查表中是否有日K线数据（peroid_type='1day'）
        （批量回测会频繁调用，做进程内缓存）
        """
        conn = None
        cursor = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT COUNT(*) as count
                FROM {table_name}
                WHERE peroid_type = '1day'
                LIMIT 1
            """
            cursor.execute(query)
            result = cursor.fetchone()
            count = result[0] if result else 0
            logger.info(f"表{table_name}中日K线数据（peroid_type='1day'）数量: {count}")
            return count > 0
        except Exception as e:
            logger.error(f"检查日K线数据失败: {e}", exc_info=True)
            return False
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if conn:
                    conn.close()

    def calculate_backtest(self, stock_code: str, table_name: str, 
                          c_points: List[Dict], r_points: List[Dict],
                          backtest_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        计算回测结果
        
        Args:
            stock_code: 股票代码
            table_name: 数据库表名
            c_points: C点列表
            r_points: R点列表
            
        Returns:
            回测结果
        """
        try:
            backtest_config = backtest_config or {}
            start_date = (backtest_config.get('startDate') or '').strip() or None
            end_date = (backtest_config.get('endDate') or '').strip() or None
            only_golden_c = bool(backtest_config.get('onlyGoldenC', False))
            exit_after_days = backtest_config.get('exitAfterDays')
            engine = (backtest_config.get('engine') or 'legacy').strip().lower()
            quiet = bool(backtest_config.get("quiet", False))
            skip_1day_check = bool(backtest_config.get("skip1dayCheck", False))
            # 批量回测：买卖价口径（可自由组合）
            # - TRIGGER_OPEN: 当日开盘
            # - TRIGGER_CLOSE: 当日收盘
            # - NEXT_OPEN: 次交易日开盘（默认，兼容旧逻辑）
            # - NEXT_CLOSE: 次交易日收盘
            buy_price_mode = (backtest_config.get("buyPriceMode") or backtest_config.get("buy_price_mode") or "").strip().upper() or None
            sell_price_mode = (backtest_config.get("sellPriceMode") or backtest_config.get("sell_price_mode") or "").strip().upper() or None
            # 兼容旧开关：useTriggerDayOpen=true 等价于 buy/sell 都用 TRIGGER_OPEN
            use_trigger_day_open = bool(backtest_config.get("useTriggerDayOpen", False))
            if use_trigger_day_open:
                buy_price_mode = buy_price_mode or "TRIGGER_OPEN"
                sell_price_mode = sell_price_mode or "TRIGGER_OPEN"
            buy_price_mode = buy_price_mode or "NEXT_OPEN"
            sell_price_mode = sell_price_mode or "NEXT_OPEN"
            # 批量回测专用开关：若最后持仓未遇到R，则按截止日/最新日“强制平仓”，把浮盈浮亏计入结果
            # 默认 False（个股回测保持“持仓中”展示习惯），batch 会显式传 True
            close_open_positions_at_end = bool(backtest_config.get("closeOpenPositionsAtEnd", False))

            def _log_info(msg: str, *args, **kwargs):
                if not quiet:
                    logger.info(msg, *args, **kwargs)

            def _log_warning(msg: str, *args, **kwargs):
                if not quiet:
                    logger.warning(msg, *args, **kwargs)

            # exitAfterDays: None/"" -> None
            try:
                if exit_after_days is None or exit_after_days == '':
                    exit_after_days_int: Optional[int] = None
                else:
                    exit_after_days_int = int(exit_after_days)
                    if exit_after_days_int <= 0:
                        exit_after_days_int = None
            except Exception:
                exit_after_days_int = None

            _log_info(f"="*60)
            _log_info(f"开始回测: 股票代码={stock_code}, 表名={table_name}")
            _log_info(f"C点数量: {len(c_points)}, R点数量: {len(r_points)}")
            _log_info(
                f"回测配置: engine={engine}, startDate={start_date}, endDate={end_date}, onlyGoldenC={only_golden_c}, exitAfterDays={exit_after_days_int}"
            )
            
            if not c_points:
                _log_warning("没有C点数据，无法回测")
                return {
                    'success': False,
                    'message': '没有C点数据',
                    'trades': [],
                    'summary': {}
                }
            
            # 批量回测提速：允许跳过 1day COUNT 检查（每个表一次 COUNT，对于 1000 股是一笔不小的 DB 开销）
            if not skip_1day_check:
                has_1day_data = self._check_1day_data_cached(table_name)
                if not has_1day_data:
                    logger.error(f"❌ 表{table_name}中没有日K线数据（peroid_type='1day'）")
                    return {
                        'success': False,
                        'message': '该股票数据库中没有日K线数据（1day），无法进行回测',
                        'trades': [],
                        'summary': {}
                    }
            
            # 按日期排序C点和R点
            sorted_c_points = sorted(c_points, key=lambda x: x.get('triggerDate') or '')
            sorted_r_points = sorted(r_points, key=lambda x: x.get('triggerDate') or '')

            # 过滤：时间区间 + 金色C
            sorted_c_points = self._filter_c_points(sorted_c_points, start_date, end_date, only_golden_c)
            sorted_r_points = self._filter_points_by_date(sorted_r_points, start_date, end_date)
            
            # 合并所有C点和R点，按时间排序，创建CR序列
            cr_sequence = []
            for c in sorted_c_points:
                cr_sequence.append({'type': 'C', 'date': c.get('triggerDate'), 'data': c})
            for r in sorted_r_points:
                cr_sequence.append({'type': 'R', 'date': r.get('triggerDate'), 'data': r})
            
            # 按日期排序
            cr_sequence = [x for x in cr_sequence if x.get('date')]
            cr_sequence.sort(key=lambda x: x['date'])
            
            _log_info(f"CR序列: {[x['type'] + x['date'] for x in cr_sequence]}")
            
            # 计算交易对：只看C-R配对，连续的C只取第一个
            trades = []
            current_c = None  # 当前持仓的C点

            # 预取：本次回测可能用到的“日K开盘价(1day)”日期集合，减少每笔交易的重复查库
            # - R模式：买入=next_trading_day(C触发日)开盘；卖出=next_trading_day(R触发日)开盘
            # - X天模式：买入同上；卖出=buy执行日 + X交易日 的当日开盘
            prefetched_open_map: Dict[str, tuple[float, str]] = {}
            prefetched_close_map: Dict[str, tuple[float, str]] = {}
            try:
                need_dates = set()
                calendar = TradingCalendarService()
                if exit_after_days_int is None:
                    for point in cr_sequence:
                        if point['type'] == 'C':
                            c_date = point.get('date')
                            if c_date:
                                need_dates.add(self._resolve_exec_day(c_date, buy_price_mode))
                        elif point['type'] == 'R':
                            r_date = point.get('date')
                            if r_date:
                                need_dates.add(self._resolve_exec_day(r_date, sell_price_mode))
                else:
                    for point in cr_sequence:
                        if point['type'] != 'C':
                            continue
                        c_date = point.get('date')
                        if not c_date:
                            continue
                        dt = datetime.strptime(c_date, '%Y-%m-%d').date()
                        buy_exec = calendar.get_next_trading_day(dt)
                        need_dates.add(buy_exec.strftime('%Y-%m-%d'))
                        sell_exec = calendar.add_trading_days(buy_exec, exit_after_days_int)
                        need_dates.add(sell_exec.strftime('%Y-%m-%d'))

                if need_dates:
                    prefetched_open_map, prefetched_close_map = self._prefetch_1day_price_maps(table_name, sorted(list(need_dates)))
            except Exception as e:
                logger.warning(f"预取日K开盘价失败，回退为逐笔查询: {e}")
                prefetched_open_map = {}
                prefetched_close_map = {}
            
            # 回测出口模式：默认按R点卖；如配置 exitAfterDays 则按“C后X交易日”卖
            if exit_after_days_int is None:
                for point in cr_sequence:
                    if point['type'] == 'C':
                        if current_c is None:
                            current_c = point['data']
                            c_date = point['date']
                            _log_info(f"新C点: {c_date}, 策略: {current_c.get('strategyName', 'N/A')}")
                        else:
                            _log_info(f"忽略连续C点: {point['date']}（已有持仓C点{current_c.get('triggerDate')}）")
                    elif point['type'] == 'R':
                        if current_c is None:
                            _log_warning(f"忽略无效R点: {point['date']}（没有对应的C点）")
                            continue

                        c_date = current_c.get('triggerDate')
                        r_date = point['date']
                        _log_info(f"找到配对: C{c_date} -> R{r_date}")

                        # 买入价：按 C 的 price_mode 执行
                        buy = self._get_1day_price_by_mode(
                            table_name=table_name,
                            trigger_date=c_date,
                            mode=buy_price_mode,
                            open_map=prefetched_open_map,
                            close_map=prefetched_close_map,
                        )
                        if buy is None:
                            _log_warning(f"⚠️ 无法获取C点{c_date}后的买入价，跳过此交易")
                            current_c = None
                            continue
                        # 卖出价：按 R 的 price_mode 执行
                        sell = self._get_1day_price_by_mode(
                            table_name=table_name,
                            trigger_date=r_date,
                            mode=sell_price_mode,
                            open_map=prefetched_open_map,
                            close_map=prefetched_close_map,
                        )
                        if sell is None:
                            _log_warning(f"⚠️ 无法获取R点{r_date}后的卖出价，跳过此交易")
                            current_c = None
                            continue

                        buy_price, buy_time = buy
                        sell_price, sell_time = sell

                        return_rate = ((sell_price - buy_price) / buy_price) * 100
                        c_datetime = datetime.strptime(c_date, '%Y-%m-%d')
                        r_datetime = datetime.strptime(r_date, '%Y-%m-%d')
                        days = (r_datetime - c_datetime).days

                        trades.append(self._build_trade_row(
                            current_c=current_c,
                            buy_price=buy_price,
                            buy_time=buy_time,
                            exit_point=point.get('data'),
                            exit_trigger_date=r_date,
                            sell_price=sell_price,
                            sell_time=sell_time,
                            return_rate=return_rate,
                            status='completed',
                            days=days,
                            exit_reason=f"R点卖出({buy_price_mode}->{sell_price_mode})"
                        ))

                        _log_info(
                            f"✅ 交易完成: C{c_date}买{buy_price}({buy_time}) -> R{r_date}卖{sell_price}({sell_time}), 收益率{return_rate:.2f}%, {days}天"
                        )
                        current_c = None
            else:
                # 仅按C点序列做交易（忽略R点）
                calendar = TradingCalendarService()
                for point in cr_sequence:
                    if point['type'] != 'C':
                        continue
                    if current_c is not None:
                        _log_info(f"忽略连续C点: {point['date']}（已有持仓C点{current_c.get('triggerDate')}）")
                        continue

                    current_c = point['data']
                    c_date = point['date']
                    _log_info(f"新C点(按X天卖出模式): {c_date}, 策略: {current_c.get('strategyName', 'N/A')}")

                    buy = self._get_next_trading_day_1day_open_with_time(table_name, c_date, prefetched_open_map)
                    if buy is None:
                        _log_warning(f"⚠️ 无法获取C点{c_date}后的买入价，跳过此交易")
                        current_c = None
                        continue
                    
                    buy_price, buy_time = buy
                    # 以“买入执行日”为起点，加X个交易日，在该日的日K开盘价卖出
                    try:
                        buy_exec_date = datetime.strptime(buy_time.split(' ')[0], '%Y-%m-%d').date()
                    except Exception:
                        buy_exec_date = datetime.strptime(c_date, '%Y-%m-%d').date()

                    sell_exec_date: date = calendar.add_trading_days(buy_exec_date, exit_after_days_int)
                    sell_trigger_date = sell_exec_date.strftime('%Y-%m-%d')
                    sell = self._get_1day_open_on_date(table_name, sell_trigger_date, prefetched_open_map)
                    if sell is None:
                        _log_warning(f"⚠️ 无法获取卖出日{sell_trigger_date}的卖出价，跳过此交易")
                        current_c = None
                        continue
                    
                    sell_price, sell_time = sell
                    return_rate = ((sell_price - buy_price) / buy_price) * 100
                    days = (sell_exec_date - buy_exec_date).days
                    
                    trades.append(self._build_trade_row(
                        current_c=current_c,
                        buy_price=buy_price,
                        buy_time=buy_time,
                        exit_point=None,
                        exit_trigger_date=sell_trigger_date,
                        sell_price=sell_price,
                        sell_time=sell_time,
                        return_rate=return_rate,
                        status='completed',
                        days=days,
                        exit_reason=f'C点后{exit_after_days_int}个交易日卖出'
                    ))
                    
                    _log_info(
                        f"✅ 交易完成(按X天): C{c_date}买{buy_price}({buy_time}) -> {sell_trigger_date}卖{sell_price}({sell_time}), 收益率{return_rate:.2f}%"
                    )
                    current_c = None
            
            # 检查是否还有未卖出的C点（持仓中）
            if current_c is not None:
                c_date = current_c['triggerDate']
                # 决定“截止日”（用于强制平仓/浮盈浮亏）
                # - 有 endDate：以 endDate 为准
                # - 无 endDate：以表内最新1day日期为准；兜底用今天
                exit_day_str = end_date or self._get_latest_1day_date(table_name) or datetime.now().strftime('%Y-%m-%d')

                # 买入价：按 C 的 price_mode 执行（若取不到且强制平仓，则回退为 TRIGGER_OPEN，避免全跳过）
                buy = self._get_1day_price_by_mode(
                    table_name=table_name,
                    trigger_date=c_date,
                    mode=buy_price_mode,
                    open_map=prefetched_open_map,
                    close_map=prefetched_close_map,
                )
                if buy is None and close_open_positions_at_end:
                    buy = self._get_1day_price_by_mode(
                        table_name=table_name,
                        trigger_date=c_date,
                        mode="TRIGGER_OPEN",
                        open_map=prefetched_open_map,
                        close_map=prefetched_close_map,
                    )
                
                if buy is not None:
                    buy_price, buy_time = buy
                    # 卖出价：虚拟R，按 R 的 price_mode 执行（以 exit_day_str 作为“触发日”）
                    sell = self._get_1day_price_by_mode(
                        table_name=table_name,
                        trigger_date=exit_day_str,
                        mode=sell_price_mode,
                        open_map=prefetched_open_map,
                        close_map=prefetched_close_map,
                    )
                    sell_price = sell[0] if sell is not None else None
                    sell_time = sell[1] if sell is not None else None

                    if sell_price is not None:
                        # 计算收益率
                        return_rate = ((sell_price - buy_price) / buy_price) * 100

                        # 计算持仓天数：以“触发C日 -> 截止日”粗略估计
                        try:
                            c_datetime = datetime.strptime(c_date, '%Y-%m-%d')
                            end_dt = datetime.strptime(exit_day_str, '%Y-%m-%d')
                            days = (end_dt - c_datetime).days
                        except Exception:
                            days = None

                        if close_open_positions_at_end:
                            # 批量回测：把截止日当作“虚拟R”强制平仓，计入 completed
                            trades.append(self._build_trade_row(
                                current_c=current_c,
                                buy_price=buy_price,
                                buy_time=buy_time,
                                exit_point=None,
                                exit_trigger_date=exit_day_str,
                                sell_price=sell_price,
                                sell_time=sell_time,
                                return_rate=return_rate,
                                status='completed',
                                days=days,
                                exit_reason=f"无R，按截止日{exit_day_str}强制卖出({buy_price_mode}->{sell_price_mode})"
                            ))
                        else:
                            # 个股回测：保持原样“持仓中”，但仍输出浮盈浮亏
                            trades.append(self._build_trade_row(
                                current_c=current_c,
                                buy_price=buy_price,
                                buy_time=buy_time,
                                exit_point=None,
                                exit_trigger_date='持仓中',
                                sell_price=sell_price,
                                sell_time=sell_time,
                                return_rate=return_rate,
                                status='holding',
                                days=days,
                                exit_reason='持仓中'
                            ))
                    else:
                        _log_warning(f"无法获取截止日/最新价格，持仓{c_date}不计入统计")
                        trades.append(self._build_trade_row(
                            current_c=current_c,
                            buy_price=buy_price,
                            buy_time=buy_time,
                            exit_point=None,
                            exit_trigger_date=None,
                            sell_price=None,
                            sell_time=None,
                            return_rate=None,
                            status='holding' if not close_open_positions_at_end else 'completed',
                            days=None,
                            exit_reason='持仓中(无最新价)' if not close_open_positions_at_end else '无R强制卖出(无最新价)'
                        ))
            
            # 计算汇总统计
            summary = self._calculate_summary(trades)
            summary['return_sum'] = summary.get('total_return', 0)  # 兼容：收益率总和（不平均）
            summary['config'] = {
                'engine': engine,
                'startDate': start_date,
                'endDate': end_date,
                'onlyGoldenC': only_golden_c,
                'exitAfterDays': exit_after_days_int,
                'useTriggerDayOpen': use_trigger_day_open,
                'buyPriceMode': buy_price_mode,
                'sellPriceMode': sell_price_mode,
                'closeOpenPositionsAtEnd': close_open_positions_at_end,
            }

            # 可选：使用 backtrader 引擎复算组合层面收益（不改变每笔交易定价规则）
            if engine == 'backtrader':
                try:
                    summary['engine_meta'] = self._run_backtrader_engine(table_name, trades)
                except Exception as e:
                    logger.error(f"backtrader 引擎运行失败，回退为legacy输出: {e}", exc_info=True)
                    summary['engine_meta'] = {'engine': 'backtrader', 'success': False, 'message': str(e)}
            
            return {
                'success': True,
                'trades': trades,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"回测失败: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'回测失败: {str(e)}',
                'trades': [],
                'summary': {}
            }
    
    def _check_30min_data(self, table_name: str) -> bool:
        """
        （已弃用）检查表中是否有30分钟K线数据
        检查表中是否有30分钟K线数据
        
        Args:
            table_name: 数据库表名
            
        Returns:
            True if 有30分钟数据, False otherwise
        """
        conn = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor()
            
            # 检查是否有peroid_type='30min'的数据
            query = f"""
                SELECT COUNT(*) as count
                FROM {table_name}
                WHERE peroid_type = '30min'
                LIMIT 1
            """
            
            cursor.execute(query)
            result = cursor.fetchone()
            count = result[0] if result else 0
            
            logger.info(f"表{table_name}中30分钟K线数据（peroid_type='30min'）数量: {count}")
            
            return count > 0
            
        except Exception as e:
            logger.error(f"检查30分钟K线数据失败: {e}", exc_info=True)
            return False
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _check_1day_data(self, table_name: str) -> bool:
        # 兼容旧调用（现在走缓存版本）
        return self._check_1day_data_cached(table_name)
    
    def _get_latest_price(self, table_name: str) -> Optional[float]:
        """
        获取最新的日K线收盘价（作为当前价格）
        
        Args:
            table_name: 数据库表名
            
        Returns:
            最新收盘价，如果找不到返回None
        """
        conn = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 查询最新的日K线收盘价
            query = f"""
                SELECT shou_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                ORDER BY shi_jian DESC
                LIMIT 1
            """
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result and result['shou_pan_jia']:
                logger.info(f"获取最新价格: {result['shi_jian']} 收盘价={result['shou_pan_jia']}")
                return float(result['shou_pan_jia'])
            else:
                logger.warning(f"未找到最新日K线数据")
                return None
                
        except Exception as e:
            logger.error(f"获取最新价格失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()
    
    def _get_next_day_30min_open(self, table_name: str, trigger_date: str) -> Optional[float]:
        """
        获取触发日期后第二天第一根30分钟K线的开盘价
        
        Args:
            table_name: 数据库表名
            trigger_date: 触发日期 (YYYY-MM-DD格式)
            
        Returns:
            开盘价，如果找不到返回None
        """
        conn = None
        try:
            # 计算第二天的日期
            trigger_dt = datetime.strptime(trigger_date, '%Y-%m-%d')
            next_day = trigger_dt + timedelta(days=1)
            next_day_str = next_day.strftime('%Y-%m-%d 00:00:00')
            
            logger.info(f"查询{trigger_date}后的30分钟K线开盘价...")
            logger.info(f"  表名: {table_name}")
            logger.info(f"  查询条件: peroid_type='30min' AND shi_jian >= '{next_day_str}'")
            
            # 查询第二天及之后的第一根30分钟K线
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 30分钟K线的peroid_type是'30min'（字符串）
            query = f"""
                SELECT kai_pan_jia, shi_jian, peroid_type
                FROM {table_name}
                WHERE peroid_type = '30min'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            
            cursor.execute(query, (next_day_str,))
            result = cursor.fetchone()
            
            if result and result['kai_pan_jia']:
                logger.info(f"✅ 找到{trigger_date}后的30分钟K线:")
                logger.info(f"  时间: {result['shi_jian']}")
                logger.info(f"  开盘价: {result['kai_pan_jia']}")
                logger.info(f"  周期类型: {result['peroid_type']}")
                return float(result['kai_pan_jia'])
            else:
                logger.warning(f"⚠️ 未找到{trigger_date}后的30分钟K线数据")
                logger.warning(f"  查询表: {table_name}")
                logger.warning(f"  查询条件: peroid_type='30min' AND shi_jian >= '{next_day_str}'")
                
                # 额外检查：看看这个日期范围内有没有任何数据
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE shi_jian >= %s LIMIT 1", (next_day_str,))
                count_result = cursor.fetchone()
                total_count = count_result['cnt'] if count_result else 0
                logger.warning(f"  该日期后总K线数: {total_count}")
                
                return None
                
        except Exception as e:
            logger.error(f"获取30分钟K线开盘价失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_next_day_30min_open_with_time(self, table_name: str, trigger_date: str) -> Optional[tuple[float, str]]:
        """
        获取触发日期后第二天第一根30分钟K线的开盘价与时间戳
        """
        conn = None
        try:
            trigger_dt = datetime.strptime(trigger_date, '%Y-%m-%d')
            next_day = trigger_dt + timedelta(days=1)
            next_day_str = next_day.strftime('%Y-%m-%d 00:00:00')

            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            query = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '30min'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query, (next_day_str,))
            result = cursor.fetchone()
            if result and result.get('kai_pan_jia') is not None and result.get('shi_jian') is not None:
                return float(result['kai_pan_jia']), str(result['shi_jian'])
            return None
        except Exception as e:
            logger.error(f"获取30分钟K线开盘价/时间失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_first_30min_open_on_date(self, table_name: str, day_str: str) -> Optional[tuple[float, str]]:
        """
        获取指定日期当天第一根30分钟K线开盘价与时间戳（shi_jian >= day 00:00:00）
        """
        conn = None
        try:
            start_ts = f"{day_str} 00:00:00"
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '30min'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query, (start_ts,))
            result = cursor.fetchone()
            if result and result.get('kai_pan_jia') is not None and result.get('shi_jian') is not None:
                return float(result['kai_pan_jia']), str(result['shi_jian'])
            return None
        except Exception as e:
            logger.error(f"获取指定日30分钟首根开盘价/时间失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_next_trading_day_1day_open_with_time(
        self,
        table_name: str,
        trigger_date: str,
        open_map: Optional[Dict[str, tuple[float, str]]] = None
    ) -> Optional[tuple[float, str]]:
        """
        获取触发日期后“次个交易日”的日K开盘价与时间戳（peroid_type='1day'）
        """
        conn = None
        try:
            trigger_dt = datetime.strptime(trigger_date, '%Y-%m-%d').date()
            next_trade_date = TradingCalendarService.get_next_trading_day(trigger_dt)
            day_str = next_trade_date.strftime('%Y-%m-%d')

            if open_map is not None:
                cached = open_map.get(day_str)
                if cached is not None:
                    return cached

            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 1) 优先：严格匹配“次个交易日当天”的 1day 开盘价
            query_exact = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) = %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query_exact, (day_str,))
            result = cursor.fetchone()
            if result and result.get('kai_pan_jia') is not None and result.get('shi_jian') is not None:
                return float(result['kai_pan_jia']), str(result['shi_jian'])

            # 2) 容错：若数据库缺该交易日 1day（常见于长假/数据未补齐），则取“>= 次交易日”的第一条 1day
            # 这样不会把整笔 C->R 交易直接丢掉；同时 buy_time/sell_time 会反映实际用到的执行日
            start_ts = f"{day_str} 00:00:00"
            query_fallback = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query_fallback, (start_ts,))
            result2 = cursor.fetchone()
            if result2 and result2.get('kai_pan_jia') is not None and result2.get('shi_jian') is not None:
                logger.warning(
                    f"⚠️ 次交易日{day_str}缺少1day数据，回退使用下一条可用1day: {result2.get('shi_jian')}"
                )
                return float(result2['kai_pan_jia']), str(result2['shi_jian'])

            return None
        except Exception as e:
            logger.error(f"获取次个交易日日K开盘价/时间失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_1day_open_on_date(
        self,
        table_name: str,
        day_str: str,
        open_map: Optional[Dict[str, tuple[float, str]]] = None
    ) -> Optional[tuple[float, str]]:
        """
        获取指定交易日 day_str 的日K开盘价与时间戳（peroid_type='1day'）
        """
        conn = None
        try:
            if open_map is not None:
                cached = open_map.get(day_str)
                if cached is not None:
                    return cached

            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) = %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query, (day_str,))
            result = cursor.fetchone()
            if result and result.get('kai_pan_jia') is not None and result.get('shi_jian') is not None:
                return float(result['kai_pan_jia']), str(result['shi_jian'])
            return None
        except Exception as e:
            logger.error(f"获取指定日K开盘价/时间失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_1day_open_on_or_after_date(
        self,
        table_name: str,
        day_str: str,
        open_map: Optional[Dict[str, tuple[float, str]]] = None
    ) -> Optional[tuple[float, str]]:
        """
        获取 day_str 当日的 1day 开盘价；若当日缺数据，则回退取 >= 当日 00:00:00 的第一条 1day。
        仅用于“同日开盘买卖”模式的容错，避免因为少量缺口导致整笔交易丢失。
        """
        if not day_str:
            return None

        # 1) 优先走 map / 严格当日
        exact = self._get_1day_open_on_date(table_name, day_str, open_map=open_map)
        if exact is not None:
            return exact

        # 2) 回退：>= 当日 00:00:00 的第一条 1day
        conn = None
        cursor = None
        try:
            start_ts = f"{day_str} 00:00:00"
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT kai_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query, (start_ts,))
            result = cursor.fetchone()
            if result and result.get('kai_pan_jia') is not None and result.get('shi_jian') is not None:
                return float(result['kai_pan_jia']), str(result['shi_jian'])
            return None
        except Exception as e:
            logger.error(f"获取当日/后续日K开盘价失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                try:
                    if cursor:
                        cursor.close()
                finally:
                    conn.close()

    def _prefetch_1day_open_map(self, table_name: str, day_strs: List[str]) -> Dict[str, tuple[float, str]]:
        """
        一次性预取多个交易日的 1day 开盘价与时间戳，减少逐笔查询。
        返回：{ 'YYYY-MM-DD': (open_price, 'YYYY-MM-DD HH:MM:SS') }
        """
        if not day_strs:
            return {}
        conn = None
        cursor = None
        try:
            # 用范围查询更通用：避免 IN 过长 / 参数个数限制
            start_ts = f"{min(day_strs)} 00:00:00"
            end_ts = f"{max(day_strs)} 23:59:59"

            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT shi_jian, kai_pan_jia
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                  AND shi_jian <= %s
                ORDER BY shi_jian ASC
            """
            cursor.execute(query, (start_ts, end_ts))
            rows = cursor.fetchall() or []
            need_set = set(day_strs)
            out: Dict[str, tuple[float, str]] = {}
            for r in rows:
                ts = r.get('shi_jian')
                op = r.get('kai_pan_jia')
                if ts is None or op is None:
                    continue
                day = str(ts)[:10]
                if day not in need_set:
                    continue
                # 只取当天最早一条（正常 1day 只有一条）
                if day not in out:
                    try:
                        out[day] = (float(op), str(ts))
                    except Exception:
                        continue
            return out
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if conn:
                    conn.close()

    def _prefetch_1day_price_maps(
        self,
        table_name: str,
        day_strs: List[str],
    ) -> tuple[Dict[str, tuple[float, str]], Dict[str, tuple[float, str]]]:
        """
        一次性预取多个交易日的 1day 开盘/收盘价与时间戳，减少逐笔查询。
        返回：(open_map, close_map)
        - open_map: { 'YYYY-MM-DD': (open_price, 'YYYY-MM-DD HH:MM:SS') }
        - close_map: { 'YYYY-MM-DD': (close_price, 'YYYY-MM-DD HH:MM:SS') }
        """
        if not day_strs:
            return {}, {}
        conn = None
        cursor = None
        try:
            start_ts = f"{min(day_strs)} 00:00:00"
            end_ts = f"{max(day_strs)} 23:59:59"

            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT shi_jian, kai_pan_jia, shou_pan_jia
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                  AND shi_jian <= %s
                ORDER BY shi_jian ASC
            """
            cursor.execute(query, (start_ts, end_ts))
            rows = cursor.fetchall() or []
            need_set = set(day_strs)
            open_map: Dict[str, tuple[float, str]] = {}
            close_map: Dict[str, tuple[float, str]] = {}
            for r in rows:
                ts = r.get('shi_jian')
                if ts is None:
                    continue
                day = str(ts)[:10]
                if day not in need_set:
                    continue
                if day not in open_map and r.get("kai_pan_jia") is not None:
                    try:
                        open_map[day] = (float(r["kai_pan_jia"]), str(ts))
                    except Exception:
                        pass
                if day not in close_map and r.get("shou_pan_jia") is not None:
                    try:
                        close_map[day] = (float(r["shou_pan_jia"]), str(ts))
                    except Exception:
                        pass
            return open_map, close_map
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if conn:
                    conn.close()

    @staticmethod
    def _resolve_exec_day(trigger_date: str, mode: str) -> str:
        """
        将“触发日 + mode”解析为执行日(YYYY-MM-DD)。
        TRIGGER_*：执行日=触发日；NEXT_*：执行日=触发日的次交易日。
        """
        d = (trigger_date or "").strip()[:10]
        m = (mode or "").strip().upper()
        if not d:
            return d
        if m.startswith("NEXT_"):
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                nd = TradingCalendarService.get_next_trading_day(dt).strftime("%Y-%m-%d")
                return nd
            except Exception:
                return d
        return d

    def _get_1day_price_by_mode(
        self,
        table_name: str,
        trigger_date: str,
        mode: str,
        open_map: Optional[Dict[str, tuple[float, str]]] = None,
        close_map: Optional[Dict[str, tuple[float, str]]] = None,
    ) -> Optional[tuple[float, str]]:
        """
        按 mode 获取执行日的 1day 开盘/收盘价（带时间戳）。
        mode: TRIGGER_OPEN/TRIGGER_CLOSE/NEXT_OPEN/NEXT_CLOSE
        """
        exec_day = self._resolve_exec_day(trigger_date, mode)
        m = (mode or "").strip().upper()
        if not exec_day:
            return None
        if m.endswith("_OPEN"):
            return self._get_1day_open_on_or_after_date(table_name, exec_day, open_map)
        if m.endswith("_CLOSE"):
            return self._get_1day_close_on_or_after_date(table_name, exec_day, close_map)
        # 兜底：未知 mode 当成 NEXT_OPEN
        return self._get_next_trading_day_1day_open_with_time(table_name, trigger_date, open_map)

    def _get_1day_close_on_or_after_date(
        self,
        table_name: str,
        day_str: str,
        close_map: Optional[Dict[str, tuple[float, str]]] = None
    ) -> Optional[tuple[float, str]]:
        """
        获取 day_str 当日的 1day 收盘价；若当日缺数据，则回退取 >= 当日 00:00:00 的第一条 1day。
        返回：(close_price, shi_jian)
        """
        if not day_str:
            return None

        if close_map is not None:
            cached = close_map.get(day_str)
            if cached is not None:
                return cached

        conn = None
        cursor = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            # 1) 严格当日
            query_exact = f"""
                SELECT shou_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND DATE(shi_jian) = %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query_exact, (day_str,))
            row = cursor.fetchone()
            if row and row.get("shou_pan_jia") is not None and row.get("shi_jian") is not None:
                return float(row["shou_pan_jia"]), str(row["shi_jian"])

            # 2) 回退：>= 当日 00:00:00 的第一条 1day
            start_ts = f"{day_str} 00:00:00"
            query_fb = f"""
                SELECT shou_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                ORDER BY shi_jian ASC
                LIMIT 1
            """
            cursor.execute(query_fb, (start_ts,))
            row2 = cursor.fetchone()
            if row2 and row2.get("shou_pan_jia") is not None and row2.get("shi_jian") is not None:
                return float(row2["shou_pan_jia"]), str(row2["shi_jian"])
            return None
        except Exception as e:
            logger.error(f"获取当日/后续日K收盘价失败: {e}", exc_info=True)
            return None
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if conn:
                    conn.close()

    def _get_latest_price_up_to(self, table_name: str, end_date: str) -> Optional[float]:
        """
        获取截止到 end_date（含）最近的日K收盘价
        """
        conn = None
        try:
            end_ts = f"{end_date} 23:59:59"
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT shou_pan_jia, shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian <= %s
                ORDER BY shi_jian DESC
                LIMIT 1
            """
            cursor.execute(query, (end_ts,))
            result = cursor.fetchone()
            if result and result.get('shou_pan_jia') is not None:
                return float(result['shou_pan_jia'])
            return None
        except Exception as e:
            logger.error(f"获取截止日最新价格失败: {e}", exc_info=True)
            return None
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _get_latest_1day_date(self, table_name: str) -> Optional[str]:
        """
        获取表内最新的 1day 日期（YYYY-MM-DD）。
        """
        conn = None
        cursor = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT shi_jian
                FROM {table_name}
                WHERE peroid_type = '1day'
                ORDER BY shi_jian DESC
                LIMIT 1
            """
            cursor.execute(query)
            row = cursor.fetchone()
            if row and row.get("shi_jian") is not None:
                return str(row["shi_jian"])[:10]
            return None
        except Exception:
            return None
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if conn:
                    conn.close()

    def _load_1day_df(self, table_name: str, start_ts: str, end_ts: str) -> pd.DataFrame:
        """
        从数据库加载 1day OHLCV，返回适配 backtrader 的 DataFrame（index=datetime）
        """
        conn = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            query = f"""
                SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang
                FROM {table_name}
                WHERE peroid_type = '1day'
                  AND shi_jian >= %s
                  AND shi_jian <= %s
                ORDER BY shi_jian ASC
            """
            cursor.execute(query, (start_ts, end_ts))
            rows = cursor.fetchall() or []
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df['datetime'] = pd.to_datetime(df['shi_jian'])
            df = df.set_index('datetime')
            df = df.rename(columns={
                'kai_pan_jia': 'open',
                'zui_gao_jia': 'high',
                'zui_di_jia': 'low',
                'shou_pan_jia': 'close',
                'cheng_jiao_liang': 'volume',
            })
            df = df[['open', 'high', 'low', 'close', 'volume']].copy()
            df['openinterest'] = 0
            for col in ['open', 'high', 'low', 'close', 'volume', 'openinterest']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            return df
        finally:
            if conn:
                cursor.close()
                conn.close()

    def _run_backtrader_engine(self, table_name: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        用 backtrader 跑一遍“预定买卖时间点”的订单，输出组合层面的收益信息。
        """
        try:
            import backtrader as bt
        except Exception as e:
            return {'engine': 'backtrader', 'success': False, 'message': f'ImportError: {e}'}

        buy_times: List[datetime] = []
        sell_times: List[datetime] = []
        for t in trades:
            bt_buy = t.get('buy_time')
            bt_sell = t.get('sell_time')
            if bt_buy:
                try:
                    buy_times.append(datetime.strptime(bt_buy, '%Y-%m-%d %H:%M:%S'))
                except Exception:
                    pass
            if bt_sell:
                try:
                    sell_times.append(datetime.strptime(bt_sell, '%Y-%m-%d %H:%M:%S'))
                except Exception:
                    pass

        if not buy_times:
            return {'engine': 'backtrader', 'success': False, 'message': '无有效buy_time，无法运行引擎'}

        start_dt = min(buy_times)
        end_dt = max(sell_times) if sell_times else max(buy_times)
        start_ts = (start_dt - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')
        end_ts = (end_dt + timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')

        df = self._load_1day_df(table_name, start_ts, end_ts)
        if df.empty:
            return {'engine': 'backtrader', 'success': False, 'message': '1day数据为空，无法运行引擎'}

        buy_dates = set([d.date() for d in buy_times])
        sell_dates = set([d.date() for d in sell_times])

        class _ScheduledOrderStrategy(bt.Strategy):
            def __init__(self):
                self._buy_dates = buy_dates
                self._sell_dates = sell_dates
                self._orders_log = []

            def next_open(self):
                dt0 = self.data.datetime.datetime(0).replace(tzinfo=None)
                day = dt0.date()
                if day in self._sell_dates and self.position.size:
                    self.sell(size=self.position.size)
                if day in self._buy_dates and not self.position.size:
                    self.buy(size=1)

            def notify_order(self, order):
                if order.status in [order.Completed]:
                    self._orders_log.append({
                        'dt': self.data.datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S'),
                        'type': 'BUY' if order.isbuy() else 'SELL',
                        'price': float(order.executed.price),
                        'size': float(order.executed.size),
                        'value': float(order.executed.value),
                    })

        cerebro = bt.Cerebro(cheat_on_open=True, stdstats=False)
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.addstrategy(_ScheduledOrderStrategy)

        cerebro.broker.setcash(100000.0)
        cerebro.broker.setcommission(commission=0.0)

        results = cerebro.run()
        strat = results[0]
        final_value = float(cerebro.broker.getvalue())
        pnl = final_value - 100000.0

        return {
            'engine': 'backtrader',
            'success': True,
            'initial_cash': 100000.0,
            'final_value': round(final_value, 2),
            'pnl': round(pnl, 2),
            'orders': getattr(strat, '_orders_log', []),
            'data_range': {'start': start_ts, 'end': end_ts},
        }

    @staticmethod
    def _filter_points_by_date(points: List[Dict[str, Any]], start_date: Optional[str], end_date: Optional[str]) -> List[Dict[str, Any]]:
        if not start_date and not end_date:
            return points
        out = []
        for p in points:
            d = (p.get('triggerDate') or '').strip()
            if not d:
                continue
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            out.append(p)
        return out

    def _filter_c_points(self, c_points: List[Dict[str, Any]], start_date: Optional[str], end_date: Optional[str], only_golden: bool) -> List[Dict[str, Any]]:
        pts = self._filter_points_by_date(c_points, start_date, end_date)
        if not only_golden:
            return pts
        out = []
        for p in pts:
            if bool(p.get('isGolden', False)):
                out.append(p)
        return out

    @staticmethod
    def _build_trade_row(
        current_c: Dict[str, Any],
        buy_price: float,
        buy_time: Optional[str],
        exit_point: Optional[Dict[str, Any]],
        exit_trigger_date: Optional[str],
        sell_price: Optional[float],
        sell_time: Optional[str],
        return_rate: Optional[float],
        status: str,
        days: Optional[int],
        exit_reason: str,
    ) -> Dict[str, Any]:
        """
        统一 trade 输出结构，方便前端展示“触发原因/插件/交易时间”
        """
        r_plugins = []
        r_strategy = ''
        if exit_point:
            r_strategy = exit_point.get('strategyName', '') or ''
            r_plugins = exit_point.get('plugins', []) or []

        return {
            # 兼容旧字段
            'c_date': current_c.get('triggerDate'),
            'c_strategy': current_c.get('strategyName', ''),
            'buy_price': round(buy_price, 2) if buy_price is not None else None,
            'r_date': exit_trigger_date,
            'sell_price': round(sell_price, 2) if sell_price is not None else None,
            'return_rate': round(return_rate, 2) if return_rate is not None else None,
            'status': status,
            'days': days,

            # 新增：交易时间/原因/插件
            'buy_time': buy_time,
            'sell_time': sell_time,
            'exit_reason': exit_reason,
            'c_point_type': current_c.get('pointType'),
            'c_is_golden': bool(current_c.get('isGolden', False)),
            'c_strategy1_score': current_c.get('strategy1Score'),
            'c_strategy2_score': current_c.get('strategy2Score'),
            'c_plugins': current_c.get('plugins', []) or [],
            'r_strategy': r_strategy,
            'r_plugins': r_plugins,
        }
    
    def _calculate_summary(self, trades: List[Dict]) -> Dict[str, Any]:
        """
        计算回测汇总统计
        
        Args:
            trades: 交易列表
            
        Returns:
            汇总统计
        """
        completed_trades = [t for t in trades if t['status'] == 'completed']
        holding_trades = [t for t in trades if t['status'] == 'holding']
        
        # 获取所有有收益率的交易（包括已完成和持仓中）
        trades_with_return = [t for t in trades if t['return_rate'] is not None]
        
        if not trades_with_return:
            return {
                'total_trades': len(trades),
                'completed_trades': len(completed_trades),
                'holding_trades': len(holding_trades),
                'win_rate': 0,
                'avg_return': 0,
                'total_return': 0,
                'max_return': 0,
                'min_return': 0,
                'avg_holding_days': 0,
                'win_count': 0,
                'loss_count': 0,
                'holding_return': 0  # 持仓收益
            }
        
        # 统计所有有收益的交易
        all_returns = [t['return_rate'] for t in trades_with_return]
        win_trades = [t for t in trades_with_return if t['return_rate'] > 0]
        days_list = [t['days'] for t in trades_with_return if t['days']]
        
        # 计算持仓收益
        holding_return = sum([t['return_rate'] for t in holding_trades if t['return_rate'] is not None])
        
        # 提取每笔已完成交易的“卖出日期”和“收益率”，用于前端绘制每日收益曲线
        # List of { 'date': 'YYYY-MM-DD', 'value': 12.34 }
        trade_yields = []
        for t in completed_trades:
            # 优先用 sell_time (实际成交时间)，如果没有则用 exit_trigger_date (触发卖出日)
            d_str = t.get('sell_time') or t.get('exit_trigger_date')
            if d_str and t.get('return_rate') is not None:
                # 截取 YYYY-MM-DD
                date_only = str(d_str)[:10]
                trade_yields.append({
                    'date': date_only,
                    'value': float(t['return_rate'])
                })

        return {
            'total_trades': len(trades),
            'completed_trades': len(completed_trades),
            'holding_trades': len(holding_trades),
            'win_rate': round((len(win_trades) / len(trades_with_return)) * 100, 2) if trades_with_return else 0,
            'avg_return': round(sum(all_returns) / len(all_returns), 2) if all_returns else 0,
            'total_return': round(sum(all_returns), 2) if all_returns else 0,
            'max_return': round(max(all_returns), 2) if all_returns else 0,
            'min_return': round(min(all_returns), 2) if all_returns else 0,
            'avg_holding_days': round(sum(days_list) / len(days_list), 1) if days_list else 0,
            'win_count': len(win_trades),
            'loss_count': len(trades_with_return) - len(win_trades),
            'holding_return': round(holding_return, 2),  # 持仓总收益
            'trade_yields': trade_yields  # 每日收益明细
        }

