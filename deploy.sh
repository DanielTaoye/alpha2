#!/bin/bash
# 腾讯云服务器部署脚本

echo "======================================"
echo "Alpha Strategy V2 - 服务器部署脚本"
echo "======================================"

# 设置环境变量
export ENV=server

# 停止旧的服务（如果在运行）
echo "1. 停止旧服务..."
pkill -f "python.*app.py" || echo "没有运行中的服务"

# 安装依赖
echo "2. 检查Python依赖..."
pip3 install -r requirements.txt

# 创建日志目录
echo "3. 创建日志目录..."
mkdir -p logs
mkdir -p backend/scripts/logs

# 测试数据库连接
echo "4. 测试数据库连接..."
python3 -c "
import pymysql
from config import DATABASE_CONFIG
try:
    conn = pymysql.connect(**DATABASE_CONFIG)
    print('✓ 数据库连接成功')
    conn.close()
except Exception as e:
    print(f'✗ 数据库连接失败: {e}')
    exit(1)
"

# 启动服务
echo "5. 启动服务..."
cd backend
nohup python3 app.py > ../logs/app.log 2>&1 &
echo $! > ../app.pid

# 等待服务启动
sleep 3

# 检查服务状态
if ps -p $(cat ../app.pid) > /dev/null; then
    echo "✓ 服务启动成功！"
    echo "进程ID: $(cat ../app.pid)"
    echo "访问地址: http://124.222.103.102:5000"
    echo "日志文件: logs/app.log"
else
    echo "✗ 服务启动失败，请查看日志"
    cat ../logs/app.log
    exit 1
fi

echo "======================================"
echo "部署完成！"
echo "======================================"

