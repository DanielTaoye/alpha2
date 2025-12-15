"""高分排行榜缓存服务（Redis + 定时刷新）"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional

import pymysql

from infrastructure.cache.redis_client import RedisClient
from infrastructure.logging.logger import get_logger
from infrastructure.persistence.database import DatabaseConnection
from domain.services.config_service import get_config_service
from application.services.latest_cr_point_service import LatestCRPointService
from application.services.kline_service import KLineApplicationService
from application.services.daily_chance_service import DailyChanceService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from infrastructure.external_apis.daily_chance_api import DailyChanceApiClient

logger = get_logger(__name__)


class HighScoreCacheService:
    """负责拉取策略分数并写入Redis的服务"""

    def __init__(self, max_workers: int = 100):
        self.max_workers = max_workers
        self.redis_client = RedisClient.instance().client
        self.config_service = get_config_service()

        # 复用最新CR点的计算逻辑
        kline_repo = KLineRepositoryImpl()
        kline_service = KLineApplicationService(kline_repo)

        daily_chance_repo = DailyChanceRepositoryImpl()
        api_client = DailyChanceApiClient()
        daily_chance_service = DailyChanceService(daily_chance_repo)
        daily_chance_service.api_client = api_client

        self.latest_cr_service = LatestCRPointService(
            kline_service,
            daily_chance_service
        )

        self._last_stats = {}

    # --------- 对外入口 ---------
    def refresh_scores(self) -> Dict:
        """拉取全量股票分数，写入Redis"""
        stocks = self._get_all_active_stocks()
        if not stocks:
            return {"success": False, "message": "没有可用股票"}

        s1_threshold = self.config_service.get_strategy1_threshold()
        s2_threshold = self.config_service.get_strategy2_threshold()

        results = []
        high_scores = []

        logger.info(f"🚀 开始刷新高分缓存，共 {len(stocks)} 只股票，线程 {self.max_workers}")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(
                    self._calc_score_safe,
                    stock,
                    s1_threshold,
                    s2_threshold
                ): stock for stock in stocks
            }

            for future in as_completed(future_map):
                res = future.result()
                if res:
                    results.append(res)
                    if res.get("is_high_score"):
                        high_scores.append(res)

        # 按总分排序
        high_scores.sort(key=lambda x: x.get("total_score", 0), reverse=True)

        # 写入Redis
        stats = {
            "total_stocks": len(stocks),
            "calculated": len(results),
            "high_score_count": len(high_scores),
            "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy1_threshold": s1_threshold,
            "strategy2_threshold": s2_threshold,
        }
        self._write_to_redis(high_scores, stats)
        self._last_stats = stats

        logger.info(f"✅ 高分缓存刷新完成: 高分 {len(high_scores)}/{len(results)}")
        return {"success": True, "stats": stats, "high_scores": len(high_scores)}

    def get_top_from_cache(self, limit: int = 100) -> Dict:
        """从缓存获取排行榜"""
        zset_key = RedisClient.full_key("high_score:zset")
        meta_key = RedisClient.full_key("high_score:meta")

        items = self.redis_client.zrevrange(zset_key, 0, limit - 1, withscores=True)
        stocks = []
        for raw, score in items:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            data["total_score"] = round(score, 2)
            # 补充驼峰命名，兼容前端
            if "volume_type" in data and "volumeType" not in data:
                data["volumeType"] = data.get("volume_type")
            if "volume_type_source" in data and "volumeTypeSource" not in data:
                data["volumeTypeSource"] = data.get("volume_type_source")
            stocks.append(data)

        meta = self.redis_client.get(meta_key)
        stats = None
        if meta:
            try:
                stats = json.loads(meta)
            except Exception:
                stats = None
        if not stats:
            stats = self._last_stats

        return {
            "stocks": stocks,
            "total": len(stocks),
            "service_stats": stats,
        }

    # --------- 内部方法 ---------
    def _calc_score_safe(self, stock: Dict, s1_threshold: float, s2_threshold: float) -> Optional[Dict]:
        """包装异常，返回格式化结果；异常也返回占位"""
        try:
            result = self.latest_cr_service.calculate_latest_cr_points(
                stock["code"],
                stock["table_name"],
                stock_nature=stock.get("nature")
            )
            # 即便返回 success=False 也写入占位，避免整榜空掉
            s1_score = result.get("strategy1", {}).get("score", 0) if result else 0
            s2_score = result.get("strategy2", {}).get("score", 0) if result else 0
            date_str = (result or {}).get("date") or datetime.now().strftime("%Y-%m-%d")
            # 总分 = max(策略1, 策略2) * 1.2，封顶 99
            total_score = min(max(s1_score or 0, s2_score or 0) * 1.2, 99)
            volume_type = (result or {}).get("volume_type") or (result or {}).get("realtime_volume_type")
            volume_type_source = (result or {}).get("volume_type_source")
            # 忽略阈值，统一标记 is_high_score=1 表示已写入
            return {
                "stock_code": stock["code"],
                "stock_name": stock.get("name", ""),
                "nature": stock.get("nature", "波段"),
                "strategy1_score": round(s1_score or 0, 2),
                "strategy2_score": round(s2_score or 0, 2),
                "total_score": round(total_score, 2),
                "is_high_score": 1,
                "date": date_str,
                "volume_type": volume_type,
                "volume_type_source": volume_type_source,
                # 兼容前端字段命名
                "volumeType": volume_type,
                "volumeTypeSource": volume_type_source,
            }
        except Exception as e:
            logger.error(f"计算 {stock.get('code')} 失败: {e}", exc_info=True)
            return {
                "stock_code": stock.get("code"),
                "stock_name": stock.get("name", ""),
                "nature": stock.get("nature", "波段"),
                "strategy1_score": 0,
                "strategy2_score": 0,
                "total_score": 0,
                "is_high_score": 1,  # 占位也写入，便于排查
                "date": datetime.now().strftime("%Y-%m-%d"),
                "error": str(e),
                "volume_type": None,
                "volume_type_source": None,
                "volumeType": None,
                "volumeTypeSource": None,
            }

    def _write_to_redis(self, high_scores: List[Dict], stats: Dict):
        zset_key = RedisClient.full_key("high_score:zset")
        meta_key = RedisClient.full_key("high_score:meta")

        pipe = self.redis_client.pipeline()
        pipe.delete(zset_key)
        pipe.delete(meta_key)

        for item in high_scores:
            member = json.dumps(item, ensure_ascii=False)
            pipe.zadd(zset_key, {member: item.get("total_score", 0)})

        # 元信息：最近刷新时间、阈值等
        pipe.set(meta_key, json.dumps(stats, ensure_ascii=False))

        # 设置TTL，避免陈旧数据长期占用
        pipe.expire(zset_key, 3 * 24 * 3600)
        pipe.expire(meta_key, 3 * 24 * 3600)
        pipe.execute()

    def _get_all_active_stocks(self) -> List[Dict]:
        """获取股票列表"""
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
                rows = cursor.fetchall()
                return [
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "nature": row.get("nature", "波段"),
                        "table_name": f"basic_data_{row['code'].lower()}",
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}", exc_info=True)
            return []

