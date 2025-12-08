"""手动启动流式微批服务"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = Path(backend_dir).parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, backend_dir)

from application.services.streaming_score_service import get_streaming_service
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def main():
    """启动流式微批服务"""
    print("=" * 60)
    print("启动流式微批分数计算服务")
    print("=" * 60)
    print()
    
    try:
        streaming_service = get_streaming_service()
        
        # 检查是否已在运行
        if streaming_service._is_running:
            print("⚠️  流式微批服务已在运行中")
            print()
            print("服务状态:")
            stats = streaming_service.get_stats()
            print(f"  总轮数: {stats.get('total_rounds', 0)}")
            print(f"  已处理: {stats.get('total_processed', 0)} 只")
            print(f"  高分股票: {stats.get('high_score_count', 0)} 只")
            print(f"  最后更新: {stats.get('last_round_time', 'N/A')}")
            return
        
        # 启动服务
        print("🚀 正在启动流式微批服务...")
        streaming_service.start()
        
        print("✅ 流式微批服务已启动！")
        print()
        print("服务信息:")
        print(f"  批次大小: {streaming_service.batch_size} 只/批")
        print(f"  并行线程: {streaming_service.max_workers} 线程")
        print()
        print("💡 提示:")
        print("  - 服务会在后台持续运行")
        print("  - 按 Ctrl+C 可停止服务")
        print("  - 或调用 API: POST /api/streaming/stop")
        print()
        print("=" * 60)
        print("服务运行中... (按 Ctrl+C 停止)")
        print("=" * 60)
        
        # 保持运行
        try:
            import time
            while streaming_service._is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            print("收到停止信号...")
            streaming_service.stop()
            print("✅ 流式微批服务已停止")
        
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
