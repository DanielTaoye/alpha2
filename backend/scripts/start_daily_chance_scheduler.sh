#!/bin/bash
# 启动每日机会数据定时同步服务

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 日志目录
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# PID文件
PID_FILE="$LOG_DIR/scheduler.pid"

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  服务已在运行 (PID: $PID)"
        exit 1
    else
        echo "清理旧的PID文件..."
        rm -f "$PID_FILE"
    fi
fi

# 激活虚拟环境（如果有）
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
    echo "✅ 虚拟环境已激活"
fi

# 启动服务
echo "🚀 启动每日机会数据定时同步服务..."
cd "$PROJECT_ROOT"

nohup python3 backend/scripts/daily_chance_scheduler.py > "$LOG_DIR/scheduler_output.log" 2>&1 &

# 保存PID
echo $! > "$PID_FILE"

echo "✅ 服务已启动 (PID: $(cat $PID_FILE))"
echo "📋 日志文件: $LOG_DIR/daily_chance_scheduler.log"
echo "📋 输出日志: $LOG_DIR/scheduler_output.log"
echo ""
echo "查看日志: tail -f $LOG_DIR/daily_chance_scheduler.log"
echo "停止服务: bash $SCRIPT_DIR/stop_daily_chance_scheduler.sh"

