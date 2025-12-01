#!/bin/bash
# 立即执行一次同步任务（测试用）

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 激活虚拟环境（如果有）
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
    echo "✅ 虚拟环境已激活"
fi

echo "🧪 立即执行一次同步任务（测试）..."
cd "$PROJECT_ROOT"

# 修改Python脚本临时执行一次
python3 - << 'EOF'
import sys
import os

# 添加路径
backend_dir = os.path.join(os.getcwd(), 'backend')
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.getcwd())

# 导入并执行
from scripts.daily_chance_scheduler import sync_daily_chance_job

# 执行一次同步
sync_daily_chance_job()
EOF

echo ""
echo "✅ 测试执行完成"

