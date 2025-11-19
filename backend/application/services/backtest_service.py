"""回测服务"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
import pymysql

logger = get_logger(__name__)


class BacktestService:
    """回测服务 - 计算C点买入R点卖出的收益率"""
    
    def calculate_backtest(self, stock_code: str, table_name: str, 
                          c_points: List[Dict], r_points: List[Dict]) -> Dict[str, Any]:
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
            logger.info(f"="*60)
            logger.info(f"开始回测: 股票代码={stock_code}, 表名={table_name}")
            logger.info(f"C点数量: {len(c_points)}, R点数量: {len(r_points)}")
            
            if not c_points:
                logger.warning("没有C点数据，无法回测")
                return {
                    'success': False,
                    'message': '没有C点数据',
                    'trades': [],
                    'summary': {}
                }
            
            # 先检查表中是否有30分钟K线数据
            has_30min_data = self._check_30min_data(table_name)
            if not has_30min_data:
                logger.error(f"❌ 表{table_name}中没有30分钟K线数据（peroid_type='30min'）")
                return {
                    'success': False,
                    'message': '该股票数据库中没有30分钟K线数据，无法进行回测',
                    'trades': [],
                    'summary': {}
                }
            
            # 按日期排序C点和R点
            sorted_c_points = sorted(c_points, key=lambda x: x['triggerDate'])
            sorted_r_points = sorted(r_points, key=lambda x: x['triggerDate'])
            
            # 合并所有C点和R点，按时间排序，创建CR序列
            cr_sequence = []
            for c in sorted_c_points:
                cr_sequence.append({'type': 'C', 'date': c['triggerDate'], 'data': c})
            for r in sorted_r_points:
                cr_sequence.append({'type': 'R', 'date': r['triggerDate'], 'data': r})
            
            # 按日期排序
            cr_sequence.sort(key=lambda x: x['date'])
            
            logger.info(f"CR序列: {[x['type'] + x['date'] for x in cr_sequence]}")
            
            # 计算交易对：只看C-R配对，连续的C只取第一个
            trades = []
            current_c = None  # 当前持仓的C点
            
            for idx, point in enumerate(cr_sequence):
                if point['type'] == 'C':
                    if current_c is None:
                        # 这是一个新的C点（之前没有持仓）
                        current_c = point['data']
                        c_date = point['date']
                        logger.info(f"新C点: {c_date}, 策略: {current_c.get('strategyName', 'N/A')}")
                    else:
                        # 已经有持仓了，这是连续的C点，忽略
                        logger.info(f"忽略连续C点: {point['date']}（已有持仓C点{current_c['triggerDate']}）")
                        
                elif point['type'] == 'R':
                    if current_c is None:
                        # 没有对应的C点，忽略这个R点
                        logger.warning(f"忽略无效R点: {point['date']}（没有对应的C点）")
                        continue
                    
                    # 找到了C-R配对
                    c_date = current_c['triggerDate']
                    r_date = point['date']
                    
                    logger.info(f"找到配对: C{c_date} -> R{r_date}")
                    
                    # 获取C点后第二天第一根30分钟K线的开盘价作为买入价
                    buy_price = self._get_next_day_30min_open(table_name, c_date)
                    
                    if buy_price is None:
                        logger.warning(f"⚠️ 无法获取C点{c_date}后的买入价，跳过此交易")
                        current_c = None  # 清除当前C点
                        continue
                    
                    # 获取R点后第二天第一根30分钟K线的开盘价作为卖出价
                    sell_price = self._get_next_day_30min_open(table_name, r_date)
                    
                    if sell_price is None:
                        logger.warning(f"⚠️ 无法获取R点{r_date}后的卖出价，跳过此交易")
                        current_c = None  # 清除当前C点
                        continue
                    
                    # 计算收益率
                    return_rate = ((sell_price - buy_price) / buy_price) * 100
                    
                    # 计算持仓天数
                    c_datetime = datetime.strptime(c_date, '%Y-%m-%d')
                    r_datetime = datetime.strptime(r_date, '%Y-%m-%d')
                    days = (r_datetime - c_datetime).days
                    
                    trades.append({
                        'c_date': c_date,
                        'c_strategy': current_c.get('strategyName', ''),
                        'buy_price': round(buy_price, 2),
                        'r_date': r_date,
                        'sell_price': round(sell_price, 2),
                        'return_rate': round(return_rate, 2),
                        'status': 'completed',
                        'days': days
                    })
                    
                    logger.info(f"✅ 交易完成: C{c_date}买{buy_price} -> R{r_date}卖{sell_price}, 收益率{return_rate:.2f}%, {days}天")
                    
                    # 清除当前C点（已经卖出）
                    current_c = None
            
            # 检查是否还有未卖出的C点（持仓中）
            if current_c is not None:
                c_date = current_c['triggerDate']
                buy_price = self._get_next_day_30min_open(table_name, c_date)
                
                if buy_price is not None:
                    # 获取最新价格（日K线的最新收盘价）
                    current_price = self._get_latest_price(table_name)
                    
                    if current_price is not None:
                        # 计算当前收益率
                        return_rate = ((current_price - buy_price) / buy_price) * 100
                        
                        # 计算持仓天数
                        c_datetime = datetime.strptime(c_date, '%Y-%m-%d')
                        today = datetime.now()
                        days = (today - c_datetime).days
                        
                        logger.info(f"持仓中: C{c_date}买{buy_price}，当前价{current_price}，浮动盈亏{return_rate:.2f}%，持仓{days}天")
                        
                        trades.append({
                            'c_date': c_date,
                            'c_strategy': current_c.get('strategyName', ''),
                            'buy_price': round(buy_price, 2),
                            'r_date': '持仓中',
                            'sell_price': round(current_price, 2),
                            'return_rate': round(return_rate, 2),
                            'status': 'holding',
                            'days': days
                        })
                    else:
                        logger.warning(f"无法获取最新价格，持仓{c_date}不计入统计")
                        trades.append({
                            'c_date': c_date,
                            'c_strategy': current_c.get('strategyName', ''),
                            'buy_price': round(buy_price, 2),
                            'r_date': None,
                            'sell_price': None,
                            'return_rate': None,
                            'status': 'holding',
                            'days': None
                        })
            
            # 计算汇总统计
            summary = self._calculate_summary(trades)
            
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
            'holding_return': round(holding_return, 2)  # 持仓总收益
        }

