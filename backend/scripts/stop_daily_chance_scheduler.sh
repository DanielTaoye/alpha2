#!/bin/bash
# 停止每日机会数据定时同步服务

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 日志目录
LOG_DIR="$SCRIPT_DIR/logs"

# PID文件
PID_FILE="$LOG_DIR/scheduler.pid"

# 检查PID文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  服务未运行（PID文件不存在）"
    exit 1
fi

# 读取PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  进程不存在 (PID: $PID)"
    rm -f "$PID_FILE"
    exit 1
fi

# 停止服务
echo "⛔ 停止服务 (PID: $PID)..."
kill $PID

# 等待进程结束
sleep 2

# 检查是否成功停止
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  进程未响应，强制终止..."
    kill -9 $PID
    sleep 1
fi

# 清理PID文件
rm -f "$PID_FILE"

echo "✅ 服务已停止"

