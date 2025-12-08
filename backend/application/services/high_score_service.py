"""高分股票扫描服务"""
import concurrent.futures
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import threading
from infrastructure.logging.logger import get_logger
from infrastructure.persistence.database import DatabaseConnection
from domain.services.config_service import get_config_service
import pymysql.cursors

logger = get_logger(__name__)

# 数据库连接数限制（避免超过MySQL最大连接数）
# MySQL默认最大连接数151，建议保留一些给其他操作
MAX_DB_CONNECTIONS = 100  # 最大并发数据库连接数
_db_connection_semaphore = threading.Semaphore(MAX_DB_CONNECTIONS)


class HighScoreService:
    """高分股票扫描服务 - 批量计算策略分数并筛选高分股票"""
    
    def __init__(self):
        self.config_service = get_config_service()
        # 缓存最新扫描结果
        self._scan_cache = {
            'data': [],
            'scan_time': None,
            'scan_count': 0
        }
        # 缓存有效期（秒）- 增加到60秒，减少重复扫描
        self._cache_ttl = 60
    
    def scan_high_score_stocks(
        self, 
        strategy1_threshold: float = None,
        strategy2_threshold: float = None,
        max_workers: int = 50,  # 默认50线程（I/O密集型任务，线程数可以较多）
        timeout_per_stock: float = 3.0,  # 降低单只股票超时时间
        use_cache: bool = True
    ) -> Dict:
        """
        扫描所有股票，找出高分股票
        
        Args:
            strategy1_threshold: 策略1阈值（默认从配置读取）
            strategy2_threshold: 策略2阈值（默认从配置读取）
            max_workers: 并行工作线程数
            timeout_per_stock: 单只股票计算超时时间（秒）
            use_cache: 是否使用缓存
            
        Returns:
            扫描结果，包含高分股票列表
        """
        start_time = time.time()
        
        # 检查缓存
        if use_cache and self._is_cache_valid():
            logger.info(f"📦 使用缓存的扫描结果 (缓存时间: {self._scan_cache['scan_time']})")
            return {
                'success': True,
                'data': self._scan_cache['data'],
                'scan_time': self._scan_cache['scan_time'],
                'from_cache': True,
                'total_scanned': self._scan_cache['scan_count']
            }
        
        # 获取阈值配置
        if strategy1_threshold is None:
            strategy1_threshold = self.config_service.get_strategy1_threshold()
        if strategy2_threshold is None:
            strategy2_threshold = self.config_service.get_strategy2_threshold()
        
        logger.info(f"🔍 开始扫描高分股票...")
        logger.info(f"   策略1阈值: {strategy1_threshold}, 策略2阈值: {strategy2_threshold}")
        logger.info(f"   并行线程数: {max_workers}, 最大数据库连接数: {MAX_DB_CONNECTIONS}")
        
        try:
            # 1. 获取所有活跃股票
            stocks = self._get_all_active_stocks()
            total_stocks = len(stocks)
            logger.info(f"📊 共获取到 {total_stocks} 只活跃股票")
            
            if total_stocks == 0:
                return {
                    'success': True,
                    'data': [],
                    'message': '没有找到活跃股票'
                }
            
            # 2. 并行计算每只股票的分数（批量处理，避免内存压力）
            high_score_stocks = []
            scanned_count = 0
            error_count = 0
            batch_size = max_workers * 2  # 每批处理数量 = 线程数 * 2
            
            # 使用线程池并行处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 分批处理股票，避免一次性提交所有任务
                for batch_start in range(0, total_stocks, batch_size):
                    batch_end = min(batch_start + batch_size, total_stocks)
                    batch_stocks = stocks[batch_start:batch_end]
                    
                    # 提交当前批次的任务
                    future_to_stock = {
                        executor.submit(
                            self._calculate_stock_score, 
                            stock, 
                            strategy1_threshold, 
                            strategy2_threshold
                        ): stock for stock in batch_stocks
                    }
                    
                    # 收集当前批次的结果
                    for future in concurrent.futures.as_completed(future_to_stock):
                        stock = future_to_stock[future]
                        scanned_count += 1
                        
                        try:
                            result = future.result(timeout=timeout_per_stock)
                            if result and result.get('is_high_score'):
                                high_score_stocks.append(result)
                                logger.info(f"⭐ 发现高分股票: {result['stock_code']} {result['stock_name']} "
                                           f"(策略1: {result['strategy1_score']:.2f}, 策略2: {result['strategy2_score']:.2f})")
                        except concurrent.futures.TimeoutError:
                            error_count += 1
                            if scanned_count % 500 == 0:  # 减少日志输出频率
                                logger.warning(f"⏱️ 超时: {stock['code']} {stock['name']} (已扫描 {scanned_count}/{total_stocks})")
                        except Exception as e:
                            error_count += 1
                            # 只在调试模式下输出详细错误
                            if scanned_count % 500 == 0:
                                logger.debug(f"❌ 计算失败: {stock['code']} - {str(e)}")
                        
                        # 每处理200只股票打印一次进度（减少日志输出）
                        if scanned_count % 200 == 0:
                            elapsed = time.time() - start_time
                            rate = scanned_count / elapsed if elapsed > 0 else 0
                            remaining = (total_stocks - scanned_count) / rate if rate > 0 else 0
                            logger.info(f"📈 扫描进度: {scanned_count}/{total_stocks} ({scanned_count*100//total_stocks}%) | "
                                       f"已耗时: {elapsed:.1f}s | 速度: {rate:.1f}只/s | 预计剩余: {remaining:.0f}s")
            
            # 3. 按总分排序（从高到低）
            high_score_stocks.sort(key=lambda x: x['total_score'], reverse=True)
            
            elapsed_time = time.time() - start_time
            scan_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"✅ 扫描完成! 耗时: {elapsed_time:.2f}秒")
            logger.info(f"   总计扫描: {scanned_count} 只, 高分股票: {len(high_score_stocks)} 只, 错误: {error_count} 只")
            
            # 更新缓存
            self._scan_cache = {
                'data': high_score_stocks,
                'scan_time': scan_time,
                'scan_count': scanned_count
            }
            
            return {
                'success': True,
                'data': high_score_stocks,
                'scan_time': scan_time,
                'from_cache': False,
                'total_scanned': scanned_count,
                'total_high_score': len(high_score_stocks),
                'error_count': error_count,
                'elapsed_seconds': round(elapsed_time, 2),
                'thresholds': {
                    'strategy1': strategy1_threshold,
                    'strategy2': strategy2_threshold
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 扫描高分股票失败: {e}", exc_info=True)
            return {
                'success': False,
                'message': str(e),
                'data': []
            }
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._scan_cache['scan_time']:
            return False
        
        try:
            cache_time = datetime.strptime(self._scan_cache['scan_time'], '%Y-%m-%d %H:%M:%S')
            elapsed = (datetime.now() - cache_time).total_seconds()
            return elapsed < self._cache_ttl
        except:
            return False
    
    def _get_all_active_stocks(self) -> List[Dict]:
        """从 all_stock 表获取所有未退市的股票"""
        try:
            with DatabaseConnection.get_connection_context() as conn:
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
                    code = row['code']
                    table_name = f"basic_data_{code.lower()}"
                    
                    stocks.append({
                        'code': code,
                        'name': row['name'],
                        'nature': row['nature'] or '波段',
                        'table_name': table_name
                    })
                
                return stocks
                
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}", exc_info=True)
            return []
    
    def _calculate_stock_score(
        self, 
        stock: Dict, 
        strategy1_threshold: float,
        strategy2_threshold: float
    ) -> Optional[Dict]:
        """
        计算单只股票的策略分数
        
        Returns:
            如果符合高分条件返回股票信息，否则返回None
        """
        stock_code = stock['code']
        stock_name = stock['name']
        table_name = stock['table_name']
        nature = stock['nature']
        
        try:
            # 快速检查：先获取最新K线，如果没有数据直接跳过
            from infrastructure.persistence.database import DatabaseConnection
            import pymysql.cursors
            
            # 快速检查是否有最新K线数据（提前剪枝）
            # 使用信号量限制并发数据库连接数
            try:
                with _db_connection_semaphore:  # 限制并发连接数
                    with DatabaseConnection.get_connection_context() as conn:
                        cursor = conn.cursor(pymysql.cursors.DictCursor)
                        # 检查表是否存在且有数据
                        check_sql = f"SELECT COUNT(*) as cnt FROM {table_name} LIMIT 1"
                        cursor.execute(check_sql)
                        row = cursor.fetchone()
                        if not row or row.get('cnt', 0) == 0:
                            return None  # 没有数据，直接跳过
            except:
                return None  # 表不存在或查询失败，跳过
            
            # 导入必要的服务
            from application.services.kline_service import KLineApplicationService
            from application.services.daily_chance_service import DailyChanceService
            from application.services.latest_cr_point_service import LatestCRPointService
            from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
            from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
            from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
            
            # 初始化服务（这些服务内部可能有缓存，重复创建开销不大）
            kline_repo = KLineRepositoryImpl()
            kline_service = KLineApplicationService(kline_repo)
            
            daily_chance_repo = DailyChanceRepositoryImpl()
            api_client = DailyChanceApiClient()
            daily_chance_service = DailyChanceService(daily_chance_repo)
            daily_chance_service.api_client = api_client
            
            latest_cr_service = LatestCRPointService(kline_service, daily_chance_service)
            
            # 计算最新一天的CR点
            result = latest_cr_service.calculate_latest_cr_points(stock_code, table_name)
            
            if not result.get('success'):
                return None
            
            # 获取策略分数
            strategy1_score = result.get('strategy1', {}).get('score', 0) or 0
            strategy2_score = result.get('strategy2', {}).get('score', 0) or 0
            
            # 检查是否都超过阈值
            strategy1_triggered = strategy1_score >= strategy1_threshold
            strategy2_triggered = strategy2_score >= strategy2_threshold
            
            # 两个策略都必须达到阈值才算高分股票
            if not (strategy1_triggered and strategy2_triggered):
                return None
            
            # 计算总分：取最高分 * 1.2，最高不超过99
            max_score = max(strategy1_score, strategy2_score)
            total_score = min(max_score * 1.2, 99.0)
            
            # 获取其他信息
            volume_type = result.get('volume_type', '-')
            date = result.get('date', datetime.now().strftime('%Y-%m-%d'))
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'table_name': table_name,
                'nature': nature,
                'strategy1_score': round(strategy1_score, 2),
                'strategy2_score': round(strategy2_score, 2),
                'strategy1_triggered': strategy1_triggered,
                'strategy2_triggered': strategy2_triggered,
                'max_score': round(max_score, 2),
                'total_score': round(total_score, 2),
                'volume_type': volume_type,
                'date': date,
                'is_high_score': True
            }
            
        except Exception as e:
            logger.debug(f"计算 {stock_code} 分数失败: {e}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self._scan_cache = {
            'data': [],
            'scan_time': None,
            'scan_count': 0
        }
        logger.info("🗑️ 高分股票扫描缓存已清空")


# 全局单例
_high_score_service_instance = None


def get_high_score_service() -> HighScoreService:
    """获取高分股票扫描服务单例"""
    global _high_score_service_instance
    if _high_score_service_instance is None:
        _high_score_service_instance = HighScoreService()
    return _high_score_service_instance
