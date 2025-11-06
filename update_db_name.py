# -*- coding: utf-8 -*-
"""
快速更新数据库名称的脚本
用法: python update_db_name.py 数据库名
"""

import sys
import os

if len(sys.argv) < 2:
    print("=" * 60)
    print("使用方法: python update_db_name.py 数据库名")
    print("=" * 60)
    print("\n请先运行 python test_db.py 查看可用的数据库")
    sys.exit(1)

database_name = sys.argv[1]

print("=" * 60)
print(f"正在更新数据库配置为: {database_name}")
print("=" * 60)

# 更新 backend/app.py
app_file = 'backend/app.py'
if os.path.exists(app_file):
    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换数据库名
    content = content.replace("'database': 'your_database'", f"'database': '{database_name}'")
    
    with open(app_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"[完成] 已更新 {app_file}")
else:
    print(f"[警告] 文件不存在: {app_file}")

# 更新 database_check.py
check_file = 'database_check.py'
if os.path.exists(check_file):
    with open(check_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换数据库名
    content = content.replace("'database': 'your_database'", f"'database': '{database_name}'")
    
    with open(check_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"[完成] 已更新 {check_file}")
else:
    print(f"[警告] 文件不存在: {check_file}")

print("\n" + "=" * 60)
print("配置更新完成！")
print("=" * 60)
print("\n下一步操作：")
print("1. 检查数据表: python database_check.py")
print("2. 启动系统: cd backend && python app.py")
print("3. 访问系统: http://localhost:5000")
print("=" * 60)

