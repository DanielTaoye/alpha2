#!/bin/bash
# 停止服务脚本

echo "======================================"
echo "停止 Alpha Strategy V2 服务"
echo "======================================"

if [ -f app.pid ]; then
    PID=$(cat app.pid)
    if ps -p $PID > /dev/null; then
        echo "停止进程: $PID"
        kill $PID
        sleep 2
        
        # 如果进程还在运行，强制停止
        if ps -p $PID > /dev/null; then
            echo "强制停止进程..."
            kill -9 $PID
        fi
        
        echo "✓ 服务已停止"
        rm app.pid
    else
        echo "进程 $PID 不存在"
        rm app.pid
    fi
else
    echo "没有找到 app.pid 文件"
    # 尝试通过名称杀死进程
    pkill -f "python.*app.py" && echo "✓ 服务已停止" || echo "没有运行中的服务"
fi

echo "======================================"

