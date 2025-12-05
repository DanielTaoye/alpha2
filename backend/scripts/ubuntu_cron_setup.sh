#!/bin/bash
# Ubuntu Cron定时任务配置脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/.."

echo "=========================================="
echo "Ubuntu Cron定时任务配置"
echo "=========================================="
echo "项目路径: $PROJECT_ROOT"
echo "脚本路径: $SCRIPT_DIR"
echo ""

# 创建执行脚本
RUN_SCRIPT="$SCRIPT_DIR/run_refresh_job.sh"

cat > "$RUN_SCRIPT" <<EOF
#!/bin/bash
# 定时任务执行脚本

cd "$SCRIPT_DIR"
export PYTHONPATH="$BACKEND_DIR:$PROJECT_ROOT"

# 执行刷新任务（最近90天）
/usr/bin/python3 "$SCRIPT_DIR/refresh_volume_type_production.py" --days 90 >> "$SCRIPT_DIR/logs/cron_refresh.log" 2>&1
EOF

chmod +x "$RUN_SCRIPT"
echo "✅ 执行脚本已创建: $RUN_SCRIPT"

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"
echo "✅ 日志目录已创建"

# 添加cron任务
CRON_JOB="0 17 * * * $RUN_SCRIPT"

echo ""
echo "准备添加cron任务:"
echo "  $CRON_JOB"
echo ""
read -p "是否添加到当前用户的crontab? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 检查是否已存在
    if crontab -l 2>/dev/null | grep -q "$RUN_SCRIPT"; then
        echo "⚠️  cron任务已存在，跳过添加"
    else
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        echo "✅ cron任务已添加"
    fi
    
    echo ""
    echo "当前crontab内容:"
    crontab -l
    echo ""
    echo "=========================================="
    echo "配置完成！"
    echo "=========================================="
    echo "定时任务将在每天 17:00 执行"
    echo "日志文件: $SCRIPT_DIR/logs/cron_refresh.log"
    echo ""
    echo "管理命令："
    echo "  查看cron任务: crontab -l"
    echo "  编辑cron任务: crontab -e"
    echo "  删除cron任务: crontab -r"
    echo "  查看日志: tail -f $SCRIPT_DIR/logs/cron_refresh.log"
else
    echo "已取消，未添加cron任务"
    echo ""
    echo "手动添加方式："
    echo "  运行: crontab -e"
    echo "  添加: $CRON_JOB"
fi

