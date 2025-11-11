"""每日机会数据定时同步脚本（使用APScheduler）"""
import sys
import os
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from application.services.daily_chance_service import DailyChanceService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def sync_job():
    """定时任务：同步每日机会数据"""
    logger.info("=" * 60)
    logger.info("定时任务触发：开始同步每日机会数据")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    try:
        # 初始化服务
        repository = DailyChanceRepositoryImpl()
        service = DailyChanceService(repository)
        
        # 同步所有股票数据
        result = service.sync_all_stocks_daily_chance()
        
        # 输出结果
        logger.info("=" * 60)
        logger.info("定时任务完成")
        logger.info(f"总股票数: {result['total_stocks']}")
        logger.info(f"成功: {result['success_count']} 只")
        logger.info(f"失败: {len(result['failed_stocks'])} 只")
        logger.info(f"保存记录数: {result['total_saved']}")
        
        if result['failed_stocks']:
            logger.warning(f"失败的股票: {', '.join(result['failed_stocks'])}")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"定时任务执行失败: {str(e)}", exc_info=True)


def main():
    """主函数：启动定时任务"""
    logger.info("启动每日机会数据定时同步服务")
    logger.info("定时任务配置: 每天 16:00 (4点PM) 执行")
    
    # 创建调度器
    scheduler = BlockingScheduler()
    
    # 添加定时任务：每天16:00执行
    scheduler.add_job(
        sync_job,
        trigger=CronTrigger(hour=16, minute=0),
        id='sync_daily_chance',
        name='同步每日机会数据',
        replace_existing=True
    )
    
    try:
        logger.info("定时任务服务已启动，等待执行...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("定时任务服务已停止")
        scheduler.shutdown()


if __name__ == '__main__':
    main()

