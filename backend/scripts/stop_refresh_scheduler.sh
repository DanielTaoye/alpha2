#!/bin/bash
# 停止 refresh_daily_chance 调度器的脚本

echo "🔍 查找 refresh_daily_chance scheduler 进程..."

# 查找进程
PIDS=$(pgrep -f "refresh_daily_chance.*scheduler")

if [ -z "$PIDS" ]; then
    echo "✅ 未找到运行中的进程"
    exit 0
fi

echo "找到以下进程："
ps aux | grep -E "refresh_daily_chance.*scheduler" | grep -v grep

echo ""
read -p "确认要停止这些进程吗？(y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    for PID in $PIDS; do
        echo "🛑 停止进程 PID: $PID"
        kill "$PID"
    done
    
    # 等待进程结束
    sleep 2
    
    # 检查是否还有进程
    REMAINING=$(pgrep -f "refresh_daily_chance.*scheduler")
    if [ -n "$REMAINING" ]; then
        echo "⚠️  部分进程仍在运行，强制停止..."
        pkill -9 -f "refresh_daily_chance.*scheduler"
        sleep 1
    fi
    
    echo "✅ 所有进程已停止"
else
    echo "❌ 已取消"
fi









