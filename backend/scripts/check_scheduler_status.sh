#!/bin/bash
# 检查定时同步服务状态

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 日志目录
LOG_DIR="$SCRIPT_DIR/logs"

# PID文件
PID_FILE="$LOG_DIR/scheduler.pid"

echo "=========================================="
echo "每日机会数据定时同步服务状态"
echo "=========================================="

# 检查PID文件
if [ ! -f "$PID_FILE" ]; then
    echo "状态: ⛔ 未运行"
    exit 0
fi

# 读取PID
PID=$(cat "$PID_FILE")

# 检查进程
if ps -p $PID > /dev/null 2>&1; then
    echo "状态: ✅ 运行中"
    echo "PID: $PID"
    echo ""
    
    # 显示进程信息
    echo "进程信息:"
    ps -p $PID -o pid,ppid,cmd,%cpu,%mem,etime
    
    echo ""
    echo "日志文件:"
    echo "  - $LOG_DIR/daily_chance_scheduler.log"
    echo "  - $LOG_DIR/scheduler_output.log"
    
    echo ""
    echo "最近的日志 (最后10行):"
    echo "----------------------------------------"
    tail -n 10 "$LOG_DIR/daily_chance_scheduler.log" 2>/dev/null || echo "日志文件不存在"
    
else
    echo "状态: ⚠️  PID文件存在但进程不存在"
    echo "建议: 运行 stop 脚本清理，然后重新启动"
fi

echo "=========================================="

