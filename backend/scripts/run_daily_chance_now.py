"""立即执行一次每日机会数据同步任务"""
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 添加项目根目录到路径
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

from scripts.daily_chance_scheduler import sync_daily_chance_job
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

if __name__ == '__main__':
    print("=" * 80)
    print("🚀 立即执行每日机会数据同步任务")
    print("=" * 80)
    print()
    
    try:
        sync_daily_chance_job()
        print()
        print("=" * 80)
        print("✅ 任务执行完成！")
        print("=" * 80)
    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ 任务执行失败: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)
