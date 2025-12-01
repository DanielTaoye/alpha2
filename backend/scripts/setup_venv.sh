#!/bin/bash
# 创建虚拟环境并安装依赖

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo "创建Python虚拟环境"
echo "=========================================="
echo "项目目录: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

# 检查python3是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: python3 未安装"
    echo "请先安装: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# 检查python3-venv是否安装
if ! python3 -m venv --help &> /dev/null; then
    echo "⚠️  python3-venv 未安装，正在安装..."
    sudo apt update
    
    # 获取Python版本
    PYTHON_VERSION=$(python3 --version | awk '{print $2}' | cut -d. -f1,2)
    echo "检测到Python版本: $PYTHON_VERSION"
    
    # 安装对应版本的venv
    sudo apt install -y python${PYTHON_VERSION}-venv python3-pip
    
    if [ $? -ne 0 ]; then
        echo "❌ 安装失败，请手动执行："
        echo "   sudo apt update"
        echo "   sudo apt install -y python${PYTHON_VERSION}-venv python3-pip"
        exit 1
    fi
    
    echo "✅ python3-venv 安装成功"
fi

# 创建虚拟环境
VENV_DIR="$PROJECT_ROOT/venv"

if [ -d "$VENV_DIR" ]; then
    echo "⚠️  虚拟环境已存在: $VENV_DIR"
    read -p "是否删除并重新创建? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        echo "✅ 已删除旧的虚拟环境"
    else
        echo "⛔ 取消操作"
        exit 0
    fi
fi

echo "🔧 创建虚拟环境: $VENV_DIR"
python3 -m venv "$VENV_DIR"

if [ $? -ne 0 ]; then
    echo "❌ 创建虚拟环境失败"
    exit 1
fi

echo "✅ 虚拟环境创建成功"
echo ""

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 升级pip
echo "🔧 升级pip..."
pip install --upgrade pip

# 安装依赖
echo ""
echo "🔧 安装项目依赖..."
echo "=========================================="

if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install -r "$PROJECT_ROOT/requirements.txt"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "=========================================="
        echo "✅ 所有依赖安装成功"
        echo "=========================================="
    else
        echo ""
        echo "=========================================="
        echo "❌ 依赖安装失败"
        echo "=========================================="
        exit 1
    fi
else
    echo "⚠️  未找到 requirements.txt，手动安装必要的包..."
    pip install Flask==3.0.0 Flask-CORS==4.0.0 pymysql==1.1.0 requests==2.31.0 APScheduler==3.10.4
fi

echo ""
echo "=========================================="
echo "🎉 虚拟环境设置完成"
echo "=========================================="
echo ""
echo "📌 使用方法:"
echo "  1. 激活虚拟环境:"
echo "     source $VENV_DIR/bin/activate"
echo ""
echo "  2. 运行脚本:"
echo "     python backend/scripts/daily_chance_scheduler.py"
echo ""
echo "  3. 退出虚拟环境:"
echo "     deactivate"
echo ""
echo "=========================================="

