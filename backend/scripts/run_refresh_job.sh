#!/bin/bash
# 定时任务执行脚本（由cron调用）

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 设置Python路径
export PYTHONPATH="$BACKEND_DIR:$PROJECT_ROOT"

# 切换到脚本目录
cd "$SCRIPT_DIR"

# 创建日志目录
mkdir -p logs

# 执行刷新任务（最近90天）
/usr/bin/python3 "$SCRIPT_DIR/refresh_volume_type_production.py" --days 90 >> "$SCRIPT_DIR/logs/cron_refresh.log" 2>&1

