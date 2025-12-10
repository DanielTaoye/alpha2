"""高分缓存定时任务"""
from datetime import datetime, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from infrastructure.logging.logger import get_logger
from application.services.high_score_cache_service import HighScoreCacheService

logger = get_logger(__name__)


class HighScoreScheduler:
    """负责定时刷新高分排行榜"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.cache_service = HighScoreCacheService()
        self._started = False

    def start(self):
        if self._started:
            return

        # 每天9:30触发首轮全量刷新
        self.scheduler.add_job(
            self.cache_service.refresh_scores,
            CronTrigger(hour=9, minute=30, timezone="Asia/Shanghai"),
            id="high_score_daily_930",
            replace_existing=True,
        )

        # 之后每分钟刷新一次（默认从09:31开始；如果当前已过则立即开始）
        now = datetime.now()
        start_after_930 = datetime.combine(now.date(), dt_time(hour=9, minute=31))
        start_date = now if now >= start_after_930 else start_after_930

        self.scheduler.add_job(
            self.cache_service.refresh_scores,
            IntervalTrigger(minutes=1, start_date=start_date),
            id="high_score_every_minute",
            replace_existing=True,
        )

        self.scheduler.start()
        self._started = True
        logger.info("✅ 高分缓存定时任务已启动: 每天09:30全量刷新，之后每分钟增量刷新")

    def shutdown(self):
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("🛑 高分缓存定时任务已关闭")


# 单例入口
_scheduler_instance = None


def get_high_score_scheduler() -> HighScoreScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = HighScoreScheduler()
    return _scheduler_instance

