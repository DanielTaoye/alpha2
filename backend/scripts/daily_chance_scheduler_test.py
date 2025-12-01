"""
测试脚本：立即执行一次同步任务
用于本地测试或手动触发
"""
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 添加项目根目录到路径
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

from scripts.daily_chance_scheduler import sync_daily_chance_job

if __name__ == '__main__':
    print("🧪 立即执行一次同步任务（测试模式）")
    print("-" * 80)
    
    try:
        sync_daily_chance_job()
    except KeyboardInterrupt:
        print("\n⛔ 用户取消")
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()

