"""
使用 APScheduler 定时全量刷新 Redis 榜单：
- 每天 9:30 启动一轮循环，持续到当天 15:00，期间一轮结束立刻再跑下一轮。
- 依赖：APScheduler（pip install apscheduler）。

运行示例（前台）：
    PYTHONPATH=. PYTHONUTF8=1 python scripts/schedule_fill_top_n.py

后台运行可用 nohup/supervisor/systemd：
    nohup env PYTHONPATH=. PYTHONUTF8=1 python scripts/schedule_fill_top_n.py > schedule_fill.log 2>&1 &
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "fill_top_n_to_redis.py"


def _run_once(top_n: str, max_workers: str):
    """调用 fill_top_n_to_redis.py 执行一轮."""
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    env.setdefault("PYTHONUTF8", "1")
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        top_n,
        max_workers,
    ]
    print(f"[{datetime.now():%F %T}] start run: {' '.join(cmd)}")
    try:
        subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            check=True,
        )
        print(f"[{datetime.now():%F %T}] run success")
    except subprocess.CalledProcessError as exc:
        print(f"[{datetime.now():%F %T}] run failed, returncode={exc.returncode}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now():%F %T}] run exception: {exc}")


def _run_loop_until_15():
    """从当前时刻开始，持续跑到当天 15:00（含），一轮完立即下一轮。"""
    top_n = os.getenv("TOP_N", "999999")  # 全量
    max_workers = os.getenv("MAX_WORKERS", "100")

    now = datetime.now()
    end = now.replace(hour=15, minute=0, second=0, microsecond=0)
    if now > end:
        print(f"[{now:%F %T}] 已过 15:00，跳过今日")
        return

    while datetime.now() <= end:
        _run_once(top_n, max_workers)
        # 防止极短时间内过多循环，可按需小睡；这里不 sleep，确保一轮完立即下一轮
        if datetime.now() > end:
            break


def main():
    scheduler = BlockingScheduler()
    # 每天 9:30 触发（如需仅工作日可加 day_of_week="mon-fri"）
    scheduler.add_job(_run_loop_until_15, "cron", hour=9, minute=30, id="fill_top_n_daily")
    print("APScheduler started. Cron: 09:30 daily until 15:00 loop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    main()

