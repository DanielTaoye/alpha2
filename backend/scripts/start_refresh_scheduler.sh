#!/bin/bash
# 启动 refresh_daily_chance 调度器的脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$BACKEND_DIR")"
LOG_FILE="$SCRIPT_DIR/logs/refresh_daily_chance_scheduler.log"

# 确保日志目录存在
mkdir -p "$SCRIPT_DIR/logs"

# 检查是否已有进程在运行
EXISTING_PIDS=$(pgrep -f "refresh_daily_chance.*scheduler")
if [ -n "$EXISTING_PIDS" ]; then
    echo "⚠️  检测到已有 refresh_daily_chance scheduler 进程在运行"
    echo ""
    echo "运行中的进程："
    ps aux | grep -E "refresh_daily_chance.*scheduler" | grep -v grep
    echo ""
    echo "⚠️  重要：如果启动多个进程，会导致任务重复执行！"
    echo ""
    echo "请选择："
    echo "  1) 停止旧进程并启动新的（推荐）"
    echo "  2) 取消"
    read -p "请输入选择 (1/2): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[1]$ ]]; then
        echo "🛑 停止旧进程..."
        for PID in $EXISTING_PIDS; do
            kill "$PID" 2>/dev/null
        done
        sleep 2
        # 如果还有进程，强制停止
        REMAINING=$(pgrep -f "refresh_daily_chance.*scheduler")
        if [ -n "$REMAINING" ]; then
            pkill -9 -f "refresh_daily_chance.*scheduler" 2>/dev/null
            sleep 1
        fi
        echo "✅ 旧进程已停止"
    else
        echo "❌ 已取消"
        exit 1
    fi
fi

# 切换到 backend 目录
cd "$BACKEND_DIR" || exit 1

# 启动后台任务
echo "🚀 启动 refresh_daily_chance scheduler..."
echo "   日志文件: $LOG_FILE"
echo "   使用 Ctrl+C 停止（或使用 stop_refresh_scheduler.sh）"

nohup env PYTHONPATH=. PYTHONUTF8=1 python3 scripts/refresh_daily_chance.py --scheduler > "$LOG_FILE" 2>&1 &

# 获取进程 PID
PID=$!
echo "✅ 进程已启动，PID: $PID"
echo ""
echo "📋 检查进程状态："
echo "   ps aux | grep refresh_daily_chance"
echo "   或运行: python3 scripts/check_scheduler_status.py"
echo ""
echo "📄 查看日志："
echo "   tail -f $LOG_FILE"
echo ""
echo "🛑 停止进程："
echo "   kill $PID"
echo "   或运行: ./scripts/stop_refresh_scheduler.sh"

