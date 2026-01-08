"""
检查 APScheduler 任务状态的工具脚本

用法：
    python scripts/check_scheduler_status.py
    python scripts/check_scheduler_status.py --job-id refresh_daily_chance
"""
import sys
import os
import argparse
import psutil
from datetime import datetime

# 添加路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.jobstores.memory import MemoryJobStore
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    print("⚠️  APScheduler 未安装")


def find_python_processes(script_name: str = None):
    """查找运行指定脚本的 Python 进程"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline'] or []
                cmdline_str = ' '.join(cmdline) if cmdline else ''
                
                # 如果指定了脚本名，检查是否匹配
                if script_name:
                    if script_name in cmdline_str:
                        processes.append({
                            'pid': proc.info['pid'],
                            'cmdline': cmdline_str,
                            'create_time': datetime.fromtimestamp(proc.info['create_time']),
                            'status': proc.status()
                        })
                else:
                    # 显示所有 Python 进程
                    if 'refresh_daily_chance' in cmdline_str or 'schedule_fill_top_n' in cmdline_str:
                        processes.append({
                            'pid': proc.info['pid'],
                            'cmdline': cmdline_str,
                            'create_time': datetime.fromtimestamp(proc.info['create_time']),
                            'status': proc.status()
                        })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return processes


def check_scheduler_jobs():
    """检查 APScheduler 任务（需要访问调度器实例，这里只能提供检查方法）"""
    print("\n" + "=" * 80)
    print("📋 APScheduler Job 检查说明")
    print("=" * 80)
    print("""
APScheduler 的 job 状态无法通过外部命令直接查看，因为它是 Python 进程内部的调度器。

检查方法：
1. 查看日志文件：
   - refresh_daily_chance: backend/scripts/logs/refresh_daily_chance.log
   - schedule_fill_top_n: 查看 nohup.out 或指定的日志文件

2. 查看进程是否在运行（上面已显示）

3. 如果进程在运行，APScheduler 应该也在运行（BlockingScheduler 会阻塞主线程）

4. 检查日志中的时间戳，确认最近是否有任务执行记录
    """)


def main():
    parser = argparse.ArgumentParser(description='检查调度器进程和任务状态')
    parser.add_argument('--script', type=str, help='要检查的脚本名称（如：refresh_daily_chance.py）')
    parser.add_argument('--job-id', type=str, help='要检查的 job ID（仅显示说明）')
    args = parser.parse_args()
    
    print("=" * 80)
    print("🔍 检查调度器进程状态")
    print("=" * 80)
    
    # 查找相关进程
    script_name = args.script or None
    processes = find_python_processes(script_name)
    
    if processes:
        print(f"\n✅ 找到 {len(processes)} 个相关进程：\n")
        for i, proc in enumerate(processes, 1):
            print(f"{i}. PID: {proc['pid']}")
            print(f"   状态: {proc['status']}")
            print(f"   启动时间: {proc['create_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   命令: {proc['cmdline'][:100]}..." if len(proc['cmdline']) > 100 else f"   命令: {proc['cmdline']}")
            print()
    else:
        print("\n❌ 未找到相关进程")
        print("   可能原因：")
        print("   1. 进程已停止")
        print("   2. 进程名称不匹配")
        print("   3. 没有使用 --scheduler 参数启动")
    
    # 检查 APScheduler jobs
    if args.job_id:
        print(f"\n📋 检查 Job ID: {args.job_id}")
        check_scheduler_jobs()
    else:
        check_scheduler_jobs()
    
    print("\n" + "=" * 80)
    print("💡 提示：")
    print("   - 如果进程在运行，APScheduler 应该也在运行")
    print("   - 查看日志文件确认任务是否正常执行")
    print("   - 使用 'tail -f <日志文件>' 实时查看日志")
    print("=" * 80)


if __name__ == '__main__':
    try:
        import psutil
    except ImportError:
        print("❌ 需要安装 psutil: pip install psutil")
        sys.exit(1)
    
    main()





























































