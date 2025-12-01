#!/bin/bash
# 立即执行一次同步任务（测试用）

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 激活虚拟环境（必须）
VENV_DIR="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ 错误: 虚拟环境不存在"
    echo "请先运行: bash $SCRIPT_DIR/setup_venv.sh"
    exit 1
fi

echo "🔧 激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 检查依赖
if ! python -c "import apscheduler" 2>/dev/null; then
    echo "❌ 错误: apscheduler 未安装"
    echo "请先运行: bash $SCRIPT_DIR/setup_venv.sh"
    exit 1
fi

echo "✅ 虚拟环境已激活"
echo ""
echo "🧪 立即执行一次同步任务（测试）..."
cd "$PROJECT_ROOT"

# 执行测试脚本
python backend/scripts/daily_chance_scheduler_test.py

echo ""
echo "✅ 测试执行完成"

