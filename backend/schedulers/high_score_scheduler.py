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
        self._intraday_job_id = "high_score_intraday"

    def start(self):
        if self._started:
            return

        # 盘中刷榜：每天09:30启动 -> 15:00 自动停止
        self.scheduler.add_job(
            self._start_intraday_refresh,
            CronTrigger(hour=9, minute=30, timezone="Asia/Shanghai"),
            id="high_score_start_930",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._stop_intraday_and_finalize,
            CronTrigger(hour=15, minute=0, timezone="Asia/Shanghai"),
            id="high_score_stop_1500",
            replace_existing=True,
        )

        # 如果在运行时间内重启服务，立即补启动
        now = datetime.now()
        if dt_time(hour=9, minute=30) <= now.time() < dt_time(hour=15, minute=0):
            self._start_intraday_refresh()
        elif now.time() >= dt_time(hour=15, minute=0):
            self._stop_intraday_and_finalize()

        self.scheduler.start()
        self._started = True
        logger.info("✅ 高分缓存定时任务已启动: 09:30-15:00 每分钟刷新，15:00 收盘全量刷新")

    def _start_intraday_refresh(self):
        """启动当日盘中每分钟刷新，15:00 自动结束"""
        now = datetime.now()
        start_after_930 = datetime.combine(now.date(), dt_time(hour=9, minute=30))
        start_date = now if now >= start_after_930 else start_after_930
        end_date = datetime.combine(now.date(), dt_time(hour=15, minute=0))

        self.scheduler.add_job(
            self.cache_service.refresh_scores,
            IntervalTrigger(minutes=1, start_date=start_date, end_date=end_date),
            id=self._intraday_job_id,
            replace_existing=True,
        )
        date_key = HighScoreCacheService.build_keys().get("date_key")
        logger.info(f"📅 盘中刷新任务已启动，date_key={date_key}，截止 15:00")

    def _stop_intraday_and_finalize(self):
        """停止盘中刷新并执行一次收盘全量刷新"""
        job = self.scheduler.get_job(self._intraday_job_id)
        if job:
            self.scheduler.remove_job(self._intraday_job_id)
            logger.info("🛑 已停止盘中刷新任务")

        date_key = HighScoreCacheService.build_keys().get("date_key")
        logger.info(f"🏁 收盘全量刷新开始，date_key={date_key}")
        self.cache_service.refresh_scores(date_str=date_key)

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

