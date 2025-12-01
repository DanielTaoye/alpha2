"""CR点计算全局缓存管理器 - 单例模式"""
from typing import Dict, Optional
from datetime import datetime, timedelta
from infrastructure.logging.logger import get_logger
import threading

logger = get_logger(__name__)


class CRCacheManager:
    """CR点计算全局缓存管理器（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化缓存管理器"""
        if self._initialized:
            return
        
        from domain.services.cr_strategy_service import CRStrategyService
        
        self._initialized = True
        self._cache_data = {}  # {stock_code: {'cr_service': ..., 'last_update': ...}}
        self._cache_lock = threading.Lock()
        
        # 每个股票独立的CR策略服务实例（带缓存）
        self._cr_services: Dict[str, CRStrategyService] = {}
        
        logger.info("✅ CR缓存管理器已初始化（单例模式）")
    
    def init_stock_cache(self, stock_code: str, days: int = 30) -> None:
        """
        初始化单个股票的缓存
        
        Args:
            stock_code: 股票代码
            days: 缓存天数（默认30天）
        """
        with self._cache_lock:
            try:
                from domain.services.cr_strategy_service import CRStrategyService
                
                # 创建该股票专用的CR策略服务实例
                if stock_code not in self._cr_services:
                    self._cr_services[stock_code] = CRStrategyService()
                
                cr_service = self._cr_services[stock_code]
                
                # 计算日期范围
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                # 初始化缓存
                logger.info(f"🔄 初始化股票缓存: {stock_code}, 范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
                cr_service.init_cache(
                    stock_code,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )
                
                # 记录缓存信息
                self._cache_data[stock_code] = {
                    'last_update': datetime.now(),
                    'start_date': start_date,
                    'end_date': end_date,
                    'days': days
                }
                
                logger.info(f"✅ 股票缓存初始化完成: {stock_code}")
                
            except Exception as e:
                logger.error(f"❌ 初始化股票缓存失败: {stock_code}, {e}", exc_info=True)
    
    def init_all_stocks(self, stock_codes: list, days: int = 30) -> None:
        """
        批量初始化所有股票的缓存
        
        Args:
            stock_codes: 股票代码列表
            days: 缓存天数（默认30天）
        """
        logger.info(f"🚀 开始批量初始化缓存: {len(stock_codes)} 支股票, {days}天数据")
        
        success_count = 0
        failed_stocks = []
        
        for i, stock_code in enumerate(stock_codes, 1):
            try:
                logger.info(f"  [{i}/{len(stock_codes)}] {stock_code}")
                self.init_stock_cache(stock_code, days)
                success_count += 1
            except Exception as e:
                logger.error(f"  ❌ {stock_code} 初始化失败: {e}")
                failed_stocks.append(stock_code)
        
        logger.info(f"🎉 批量初始化完成: 成功 {success_count}/{len(stock_codes)}")
        if failed_stocks:
            logger.warning(f"  失败的股票: {', '.join(failed_stocks)}")
    
    def update_stock_cache(self, stock_code: str) -> None:
        """
        增量更新单个股票的缓存（只更新最新1天数据）
        
        Args:
            stock_code: 股票代码
        """
        with self._cache_lock:
            try:
                if stock_code not in self._cr_services:
                    # 如果缓存不存在，直接初始化
                    logger.warning(f"⚠️  股票缓存不存在，执行完整初始化: {stock_code}")
                    self.init_stock_cache(stock_code)
                    return
                
                cr_service = self._cr_services[stock_code]
                cache_info = self._cache_data.get(stock_code, {})
                
                # 计算新的日期范围（保持窗口大小不变，向前滑动）
                end_date = datetime.now()
                days = cache_info.get('days', 30)
                start_date = end_date - timedelta(days=days)
                
                # 清除旧缓存
                cr_service.clear_cache()
                
                # 重新加载缓存
                logger.debug(f"🔄 更新股票缓存: {stock_code}")
                cr_service.init_cache(
                    stock_code,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )
                
                # 更新缓存信息
                self._cache_data[stock_code]['last_update'] = datetime.now()
                self._cache_data[stock_code]['start_date'] = start_date
                self._cache_data[stock_code]['end_date'] = end_date
                
                logger.debug(f"✅ 股票缓存更新完成: {stock_code}")
                
            except Exception as e:
                logger.error(f"❌ 更新股票缓存失败: {stock_code}, {e}", exc_info=True)
    
    def get_cr_service(self, stock_code: str) -> Optional['CRStrategyService']:
        """
        获取股票的CR策略服务（带缓存）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            CR策略服务实例，如果不存在则返回None
        """
        # 如果缓存存在且有效，直接返回
        if stock_code in self._cr_services:
            # 检查缓存是否过期（超过60分钟）
            if self.is_cache_valid(stock_code, max_age_minutes=60):
                logger.debug(f"✅ 使用现有缓存: {stock_code}")
                return self._cr_services[stock_code]
            else:
                logger.info(f"⚠️  缓存已过期，更新中: {stock_code}")
                self.update_stock_cache(stock_code)
                return self._cr_services[stock_code]
        else:
            # 缓存不存在，初始化
            logger.info(f"📥 缓存不存在，初始化中: {stock_code}")
            self.init_stock_cache(stock_code)
            return self._cr_services.get(stock_code)
    
    def is_cache_valid(self, stock_code: str, max_age_minutes: int = 60) -> bool:
        """
        检查缓存是否有效（是否需要更新）
        
        Args:
            stock_code: 股票代码
            max_age_minutes: 最大缓存时间（分钟），默认60分钟
            
        Returns:
            True表示缓存有效，False表示需要更新
        """
        if stock_code not in self._cache_data:
            return False
        
        last_update = self._cache_data[stock_code].get('last_update')
        if not last_update:
            return False
        
        age = (datetime.now() - last_update).total_seconds() / 60
        return age < max_age_minutes
    
    def get_cache_info(self, stock_code: Optional[str] = None) -> dict:
        """
        获取缓存信息
        
        Args:
            stock_code: 股票代码，如果为None则返回所有股票的缓存信息
            
        Returns:
            缓存信息字典
        """
        if stock_code:
            return self._cache_data.get(stock_code, {})
        else:
            return {
                'total_stocks': len(self._cache_data),
                'stocks': list(self._cache_data.keys()),
                'details': self._cache_data
            }
    
    def clear_all_cache(self) -> None:
        """清空所有缓存"""
        with self._cache_lock:
            logger.info("🔄 清空所有缓存...")
            for cr_service in self._cr_services.values():
                cr_service.clear_cache()
            self._cr_services.clear()
            self._cache_data.clear()
            logger.info("✅ 所有缓存已清空")


# 全局单例实例
_global_cache_manager = None


def get_cr_cache_manager() -> CRCacheManager:
    """获取全局CR缓存管理器实例"""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CRCacheManager()
    return _global_cache_manager

