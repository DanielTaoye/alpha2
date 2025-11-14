"""检查被否决的C点"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 读取日志文件
log_file = os.path.join(os.path.dirname(backend_dir), 'logs', 'app.log')

print("检查最近的C点计算日志：\n")

try:
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # 倒序查找最近的日志
    for line in reversed(lines[-200:]):
        if '被插件否决' in line or '实时分析完成' in line or '触发C点' in line:
            print(line.strip())
            
except Exception as e:
    print(f"读取日志失败: {e}")

