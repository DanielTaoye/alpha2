"""数据库配置 - 自动从根目录config.py导入"""

# 从根目录的config.py导入配置
import sys
from pathlib import Path

# 添加根目录到路径
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from config import DATABASE_CONFIG

