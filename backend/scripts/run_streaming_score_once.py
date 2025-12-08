"""一次性运行流式微批服务，计算并写入所有股票的策略1和策略2分数"""
import sys
import os
from pathlib import Path
import time

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = Path(backend_dir).parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, backend_dir)

from application.services.streaming_score_service import get_streaming_service
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def main():
    """运行一次完整的分数计算和写入"""
    print("=" * 70)
    print("流式微批分数计算服务 - 一次性运行")
    print("=" * 70)
    print()
    print("功能：计算所有股票的策略1和策略2分数，并写入数据库")
    print("数据表：b_daily_chance")
    print("字段：strategy1_score, strategy2_score, total_score, is_high_score")
    print()
    print("=" * 70)
    print()
    
    try:
        streaming_service = get_streaming_service()
        
        # 检查是否已在运行
        if streaming_service._is_running:
            print("⚠️  流式微批服务已在运行中")
            print("   请先停止现有服务，或等待当前任务完成")
            print()
            stats = streaming_service.get_stats()
            print(f"当前状态:")
            print(f"  总轮数: {stats.get('total_rounds', 0)}")
            print(f"  已处理: {stats.get('total_processed', 0)} 只")
            print(f"  当前批次: {stats.get('current_batch', 0)}")
            return
        
        print("🚀 启动流式微批服务...")
        print()
        
        # 启动服务
        streaming_service.start()
        
        print("✅ 服务已启动，开始计算和写入分数...")
        print()
        print("💡 提示：")
        print("  - 服务会持续运行，计算所有股票")
        print("  - 每批处理完会立即写入数据库")
        print("  - 按 Ctrl+C 可随时停止")
        print()
        print("=" * 70)
        print("正在运行... (按 Ctrl+C 停止)")
        print("=" * 70)
        print()
        
        # 监控进度
        last_rounds = 0
        last_processed = 0
        
        try:
            while streaming_service._is_running:
                time.sleep(5)  # 每5秒检查一次
                
                stats = streaming_service.get_stats()
                current_rounds = stats.get('total_rounds', 0)
                current_processed = stats.get('total_processed', 0)
                current_batch = stats.get('current_batch', 0)
                high_score_count = stats.get('high_score_count', 0)
                
                # 显示进度
                if current_processed != last_processed or current_rounds != last_rounds:
                    print(f"📊 进度: 第 {current_rounds} 轮 | "
                          f"批次 {current_batch} | "
                          f"已处理 {current_processed} 只 | "
                          f"高分股票 {high_score_count} 只")
                    
                    if stats.get('last_round_time'):
                        print(f"   最后更新: {stats.get('last_round_time')}")
                    
                    last_rounds = current_rounds
                    last_processed = current_processed
                    print()
                
        except KeyboardInterrupt:
            print()
            print("收到停止信号...")
            streaming_service.stop()
            print("✅ 流式微批服务已停止")
            
            # 显示最终统计
            final_stats = streaming_service.get_stats()
            print()
            print("=" * 70)
            print("最终统计:")
            print("=" * 70)
            print(f"  总轮数: {final_stats.get('total_rounds', 0)}")
            print(f"  已处理: {final_stats.get('total_processed', 0)} 只")
            print(f"  高分股票: {final_stats.get('high_score_count', 0)} 只")
            print(f"  最后更新: {final_stats.get('last_round_time', 'N/A')}")
            print("=" * 70)
        
    except Exception as e:
        logger.error(f"运行失败: {e}", exc_info=True)
        print(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
