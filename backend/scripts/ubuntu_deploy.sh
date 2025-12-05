#!/bin/bash
# Ubuntu部署脚本 - 刷新成交量类型和K线组合定时任务

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/.."

echo "=========================================="
echo "Ubuntu部署 - 定时任务配置"
echo "=========================================="
echo "项目路径: $PROJECT_ROOT"
echo "脚本路径: $SCRIPT_DIR"
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装Python"
    exit 1
fi

echo "✅ Python版本: $(python3 --version)"

# 检查依赖
echo ""
echo "检查依赖包..."
python3 -c "import pymysql" 2>/dev/null || { echo "❌ 缺少 pymysql，请运行: pip3 install pymysql"; exit 1; }
python3 -c "import apscheduler" 2>/dev/null || { echo "❌ 缺少 apscheduler，请运行: pip3 install APScheduler"; exit 1; }
echo "✅ 依赖检查通过"

# 创建日志目录
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
echo "✅ 日志目录: $LOG_DIR"

# 创建systemd服务文件
SERVICE_NAME="refresh-volume-patterns"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo ""
echo "创建systemd服务文件..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=刷新生产库成交量类型和K线组合定时任务
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="PYTHONPATH=$BACKEND_DIR:$PROJECT_ROOT"
ExecStart=/usr/bin/python3 $SCRIPT_DIR/refresh_volume_type_production.py --scheduler
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/scheduler_output.log
StandardError=append:$LOG_DIR/scheduler_error.log

[Install]
WantedBy=multi-user.target
EOF

echo "✅ 服务文件已创建: $SERVICE_FILE"

# 重新加载systemd
echo ""
echo "重新加载systemd配置..."
sudo systemctl daemon-reload

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "使用以下命令管理服务："
echo "  启动服务: sudo systemctl start $SERVICE_NAME"
echo "  停止服务: sudo systemctl stop $SERVICE_NAME"
echo "  查看状态: sudo systemctl status $SERVICE_NAME"
echo "  查看日志: sudo journalctl -u $SERVICE_NAME -f"
echo "  开机自启: sudo systemctl enable $SERVICE_NAME"
echo ""
echo "或者使用cron方式（见下方说明）"
echo ""

