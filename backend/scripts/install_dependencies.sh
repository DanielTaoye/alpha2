#!/bin/bash
# 安装依赖脚本（Ubuntu/Linux）

echo "=========================================="
echo "安装Python依赖包"
echo "=========================================="

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    echo "请先安装Python: sudo apt install python3 python3-pip"
    exit 1
fi

echo "✅ Python版本: $(python3 --version)"
echo ""

# 安装依赖
echo "安装依赖包..."
pip3 install pymysql APScheduler

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo ""
echo "验证安装:"
python3 -c "import pymysql; print('✅ pymysql 已安装')"
python3 -c "import apscheduler; print('✅ APScheduler 已安装')"
echo ""

