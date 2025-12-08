"""流式微批分数计算服务 - 类似Flink的DataStream"""
import threading
import time
import queue
from typing import List, Dict, Optional
from datetime import datetime
import concurrent.futures
from infrastructure.logging.logger import get_logger
from infrastructure.persistence.database import DatabaseConnection
from domain.services.config_service import get_config_service
import pymysql
import pymysql.cursors
import sys
from pathlib import Path

logger = get_logger(__name__)


def get_master_db_connection():
    """
    获取生产主库连接（可写）
    优先使用 config_production_master.py，否则使用 config_master.py
    """
    try:
        # 尝试导入生产主库配置
        root_dir = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(root_dir))
        
        try:
            from config_production_master import DATABASE_CONFIG as MASTER_CONFIG
            logger.debug("使用生产主库配置（外网）")
        except ImportError:
            try:
                from config_master import DATABASE_CONFIG as MASTER_CONFIG
                logger.debug("使用主库配置（内网）")
            except ImportError:
                # 如果都没有，使用默认配置（可能是从库，会报错）
                logger.warning("未找到主库配置，使用默认配置（可能只读）")
                from infrastructure.config.database_config import DATABASE_CONFIG as MASTER_CONFIG
        
        return pymysql.connect(
            host=MASTER_CONFIG['host'],
            port=MASTER_CONFIG['port'],
            user=MASTER_CONFIG['user'],
            password=MASTER_CONFIG['password'],
            database=MASTER_CONFIG['database'],
            charset=MASTER_CONFIG.get('charset', 'utf8mb4'),
            autocommit=True
        )
    except Exception as e:
        logger.error(f"连接主库失败: {e}", exc_info=True)
        raise


class StreamingScoreService:
    """
    流式微批分数计算服务
    
    核心思路（类似Flink DataStream）：
    1. 将5000只股票分成微批（每批100只）
    2. 持续循环处理各批次
    3. 每批处理完立即写入数据库
    4. 前端查询直接读数据库（毫秒级）
    """
    
    def __init__(self, batch_size=100, max_workers=50):
        """
        初始化流式服务
        
        Args:
            batch_size: 每批处理的股票数量
            max_workers: 每批的并行线程数
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.config_service = get_config_service()
        
        # 流式状态
        self._is_running = False
        self._worker_thread = None
        self._stop_event = threading.Event()
        
        # 统计信息
        self._stats = {
            'total_rounds': 0,
            'total_processed': 0,
            'last_round_time': None,
            'current_batch': 0,
            'high_score_count': 0
        }
        self._stats_lock = threading.Lock()
    
    def start(self):
        """启动流式微批服务（后台线程）"""
        if self._is_running:
            logger.warning("流式微批服务已在运行中")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 启动流式微批分数计算服务")
        logger.info(f"   批次大小: {self.batch_size} 只/批")
        logger.info(f"   并行线程: {self.max_workers} 线程")
        logger.info("=" * 60)
        
        self._is_running = True
        self._stop_event.clear()
        
        # 启动后台工作线程
        self._worker_thread = threading.Thread(
            target=self._streaming_worker,
            name="StreamingScoreWorker",
            daemon=True
        )
        self._worker_thread.start()
        
        logger.info("✅ 流式微批服务已启动（后台运行）")
    
    def stop(self):
        """停止流式微批服务"""
        if not self._is_running:
            return
        
        logger.info("⏸️  正在停止流式微批服务...")
        self._stop_event.set()
        self._is_running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        
        logger.info("✅ 流式微批服务已停止")
    
    def get_stats(self) -> Dict:
        """获取服务统计信息"""
        with self._stats_lock:
            return self._stats.copy()
    
    def _streaming_worker(self):
        """流式工作线程 - 持续循环处理"""
        logger.info("🔄 流式工作线程已启动，开始持续处理...")
        
        while not self._stop_event.is_set():
            try:
                round_start = time.time()
                
                # 执行一轮完整的微批处理
                self._process_one_round()
                
                round_time = time.time() - round_start
                
                with self._stats_lock:
                    self._stats['total_rounds'] += 1
                    self._stats['last_round_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                logger.info(f"✅ 完成第 {self._stats['total_rounds']} 轮，耗时: {round_time:.1f}秒")
                logger.info(f"   高分股票: {self._stats['high_score_count']} 只")
                
                # 短暂休息（避免过度占用资源）
                if not self._stop_event.wait(timeout=2):
                    continue
                else:
                    break
                    
            except Exception as e:
                logger.error(f"❌ 流式处理出错: {e}", exc_info=True)
                # 出错后等待10秒再继续
                if not self._stop_event.wait(timeout=10):
                    continue
                else:
                    break
        
        logger.info("🛑 流式工作线程已退出")
    
    def _process_one_round(self):
        """处理一轮完整的微批"""
        # 1. 获取所有股票
        stocks = self._get_all_active_stocks()
        total_stocks = len(stocks)
        
        if total_stocks == 0:
            logger.warning("⚠️ 没有活跃股票，跳过本轮")
            return
        
        # 获取阈值
        strategy1_threshold = self.config_service.get_strategy1_threshold()
        strategy2_threshold = self.config_service.get_strategy2_threshold()
        
        # 2. 分批处理
        total_batches = (total_stocks + self.batch_size - 1) // self.batch_size
        high_score_count = 0
        
        logger.info(f"📊 开始新一轮: {total_stocks} 只股票，分 {total_batches} 批")
        
        for batch_idx in range(total_batches):
            if self._stop_event.is_set():
                logger.info("⏸️  收到停止信号，中断当前轮次")
                break
            
            batch_start = batch_idx * self.batch_size
            batch_end = min(batch_start + self.batch_size, total_stocks)
            batch_stocks = stocks[batch_start:batch_end]
            
            # 更新当前批次
            with self._stats_lock:
                self._stats['current_batch'] = batch_idx + 1
            
            # 3. 并行计算当前批次
            batch_result = self._process_batch(
                batch_stocks,
                strategy1_threshold,
                strategy2_threshold
            )
            
            # 4. 批量更新数据库
            if batch_result:
                logger.debug(f"   批次 {batch_idx+1}: 准备更新 {len(batch_result)} 条记录")
                updated_count = self._batch_update_database(batch_result)
                logger.info(f"   批次 {batch_idx+1}/{total_batches}: 处理 {len(batch_stocks)} 只，计算成功 {len(batch_result)} 只，更新 {updated_count} 条")
            else:
                updated_count = 0
                logger.debug(f"   批次 {batch_idx+1}/{total_batches}: 处理 {len(batch_stocks)} 只，无计算结果")
            
            high_score_count += len([r for r in batch_result if r.get('is_high_score')])
            
            with self._stats_lock:
                self._stats['total_processed'] += len(batch_stocks)
                self._stats['high_score_count'] = high_score_count
    
    def _process_batch(
        self,
        batch_stocks: List[Dict],
        strategy1_threshold: float,
        strategy2_threshold: float
    ) -> List[Dict]:
        """并行处理一个批次"""
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._calculate_stock_score,
                    stock,
                    strategy1_threshold,
                    strategy2_threshold
                ): stock for stock in batch_stocks
            }
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=3)
                    if result:
                        results.append(result)
                except Exception as e:
                    stock = futures[future]
                    logger.debug(f"计算失败: {stock['code']} - {e}")
        
        return results
    
    def _calculate_stock_score(
        self,
        stock: Dict,
        strategy1_threshold: float,
        strategy2_threshold: float
    ) -> Optional[Dict]:
        """计算单只股票的分数（简化版，快速计算）"""
        stock_code = stock['code']
        table_name = stock['table_name']
        
        try:
            # 导入服务
            from application.services.kline_service import KLineApplicationService
            from application.services.daily_chance_service import DailyChanceService
            from application.services.latest_cr_point_service import LatestCRPointService
            from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
            from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
            from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient
            
            kline_repo = KLineRepositoryImpl()
            kline_service = KLineApplicationService(kline_repo)
            
            daily_chance_repo = DailyChanceRepositoryImpl()
            api_client = DailyChanceApiClient()
            daily_chance_service = DailyChanceService(daily_chance_repo)
            daily_chance_service.api_client = api_client
            
            latest_cr_service = LatestCRPointService(kline_service, daily_chance_service)
            
            # 计算分数
            result = latest_cr_service.calculate_latest_cr_points(stock_code, table_name)
            
            if not result.get('success'):
                logger.debug(f"计算失败: {stock_code} - {result.get('message', '未知错误')}")
                return None
            
            strategy1_score = result.get('strategy1', {}).get('score', 0) or 0
            strategy2_score = result.get('strategy2', {}).get('score', 0) or 0
            
            # 获取日期（确保格式正确）
            result_date = result.get('date')
            if not result_date:
                # 如果没有日期，使用今天
                result_date = datetime.now().strftime('%Y-%m-%d')
            elif isinstance(result_date, datetime):
                result_date = result_date.strftime('%Y-%m-%d')
            elif isinstance(result_date, str):
                # 如果包含时间部分，只取日期部分
                result_date = result_date.split(' ')[0].split('T')[0]
            
            # 验证日期格式
            try:
                datetime.strptime(result_date, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"日期格式错误: {result_date}，使用今天日期")
                result_date = datetime.now().strftime('%Y-%m-%d')
            
            # 判断是否高分
            is_high_score = (strategy1_score >= strategy1_threshold and 
                           strategy2_score >= strategy2_threshold)
            
            # 计算总分
            max_score = max(strategy1_score, strategy2_score)
            total_score = min(max_score * 1.2, 99.0)
            
            # 获取股票名称和股性（从stock字典或从数据库）
            stock_name = stock.get('name', '')
            stock_nature = stock.get('nature', '波段')
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'nature': stock_nature,
                'date': result_date,
                'strategy1_score': round(strategy1_score, 2),
                'strategy2_score': round(strategy2_score, 2),
                'total_score': round(total_score, 2),
                'is_high_score': 1 if is_high_score else 0
            }
            
        except Exception as e:
            logger.debug(f"计算 {stock_code} 失败: {e}")
            return None
    
    def _batch_update_database(self, results: List[Dict]) -> int:
        """批量更新数据库（使用主库，使用UPSERT确保记录存在）"""
        if not results:
            return 0
        
        conn = None
        try:
            # 使用主库连接（可写）
            conn = get_master_db_connection()
            cursor = conn.cursor()
            
            # 使用 INSERT ... ON DUPLICATE KEY UPDATE 确保记录存在
            # 如果记录不存在，会先插入基本字段，然后更新分数字段
            sql = """
                INSERT INTO b_daily_chance 
                (stock_code, stock_name, stock_nature, date, 
                 strategy1_score, strategy2_score, total_score, is_high_score, score_updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    strategy1_score = VALUES(strategy1_score),
                    strategy2_score = VALUES(strategy2_score),
                    total_score = VALUES(total_score),
                    is_high_score = VALUES(is_high_score),
                    score_updated_at = NOW()
            """
            
            # 需要获取股票名称和股性（从计算结果的原始数据或从数据库查询）
            batch_data = []
            for r in results:
                # 尝试从结果中获取股票信息，如果没有则使用默认值
                stock_name = r.get('stock_name', '')
                stock_nature = r.get('nature', '波段')
                
                # 确保日期格式正确（YYYY-MM-DD）
                date_str = r['date']
                if isinstance(date_str, datetime):
                    date_str = date_str.strftime('%Y-%m-%d')
                elif isinstance(date_str, str):
                    # 如果包含时间部分，只取日期部分
                    date_str = date_str.split(' ')[0].split('T')[0]
                
                # 确保股票代码格式正确（大写）
                stock_code = str(r['stock_code']).upper()
                
                batch_data.append((
                    stock_code,
                    stock_name,
                    stock_nature,
                    date_str,
                    r['strategy1_score'],
                    r['strategy2_score'],
                    r['total_score'],
                    r['is_high_score']
                ))
            
            # 执行批量更新
            cursor.executemany(sql, batch_data)
            conn.commit()
            updated_count = cursor.rowcount
            
            # 详细日志（显示前3条）
            if results and len(results) > 0:
                logger.info(f"📝 批量更新示例（前3条）:")
                for i, sample in enumerate(results[:3], 1):
                    date_str = sample['date']
                    if isinstance(date_str, datetime):
                        date_str = date_str.strftime('%Y-%m-%d')
                    elif isinstance(date_str, str):
                        date_str = date_str.split(' ')[0].split('T')[0]
                    
                    logger.info(f"  {i}. {sample['stock_code']} {date_str} - "
                              f"策略1:{sample['strategy1_score']}, "
                              f"策略2:{sample['strategy2_score']}, "
                              f"总分:{sample['total_score']}, "
                              f"高分:{sample['is_high_score']}")
            
            logger.info(f"✅ 批量更新完成: {len(results)} 条记录，实际影响 {updated_count} 行")
            
            # 如果更新行数为0，可能是日期或股票代码不匹配，记录警告
            if updated_count == 0 and len(results) > 0:
                logger.warning(f"⚠️  警告：更新了0行，可能是日期或股票代码不匹配")
                logger.warning(f"   示例数据: stock_code={results[0].get('stock_code')}, date={results[0].get('date')}")
                logger.warning(f"   请检查数据库中的日期格式和股票代码格式")
            
            return updated_count
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"批量更新数据库失败: {e}", exc_info=True)
            logger.error(f"失败的数据示例: {results[0] if results else '无数据'}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def _get_all_active_stocks(self) -> List[Dict]:
        """获取所有活跃股票（可以使用从库，只读）"""
        try:
            # 读取操作可以使用默认连接（可能是从库）
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
                
                return [
                    {
                        'code': row['code'],
                        'name': row['name'],
                        'nature': row.get('nature', '波段'),
                        'table_name': f"basic_data_{row['code'].lower()}"
                    }
                    for row in results
                ]
                
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}", exc_info=True)
            return []


# 全局单例
_streaming_service_instance = None
_service_lock = threading.Lock()


def get_streaming_service() -> StreamingScoreService:
    """获取流式微批服务单例"""
    global _streaming_service_instance
    if _streaming_service_instance is None:
        with _service_lock:
            if _streaming_service_instance is None:
                _streaming_service_instance = StreamingScoreService()
    return _streaming_service_instance
