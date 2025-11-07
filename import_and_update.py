#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键导入并更新股票数据
从生产环境拉取45支股票数据并更新本地配置
"""

import sys
import os
from datetime import datetime

# 设置Windows控制台编码
if sys.platform == 'win32':
    import locale
    # 使用更安全的方式设置编码
    try:
        # Python 3.7+
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass


def print_header():
    """打印标题"""
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "股票数据导入与配置更新工具" + " " * 20 + "║")
    print("╚" + "═" * 68 + "╝")
    print()


def print_section(title):
    """打印分段标题"""
    print("\n" + "─" * 70)
    print(f"  {title}")
    print("─" * 70)


def confirm_operation():
    """确认操作"""
    print("\n本操作将：")
    print("  1. 从生产环境（腾讯云）拉取45支股票的基本信息")
    print("  2. 从生产环境拉取45支股票的K线数据")
    print("  3. 将数据导入到本地MySQL数据库")
    print("  4. 更新 backend/app.py 配置文件")
    print("  5. 将每个股性分组从5支扩展到20支")
    print()
    print("股票分类：")
    print("  - 波段：20支")
    print("  - 短线：20支")
    print("  - 中长线：20支")
    print()
    
    while True:
        choice = input("确认执行？(y/n): ").strip().lower()
        if choice in ['y', 'yes', '是']:
            return True
        elif choice in ['n', 'no', '否']:
            return False
        else:
            print("请输入 y 或 n")


def run_import():
    """运行导入脚本"""
    print_section("步骤 1/2: 导入股票数据")
    
    try:
        # 导入脚本模块
        import import_stocks_from_prod
        
        # 执行导入
        import_stocks_from_prod.main()
        return True
        
    except Exception as e:
        print(f"\n✗ 导入数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_update():
    """运行更新配置脚本"""
    print_section("步骤 2/2: 更新应用配置")
    
    try:
        # 导入脚本模块
        import update_app_config
        
        # 执行更新
        return update_app_config.update_app_config()
        
    except Exception as e:
        print(f"\n✗ 更新配置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    start_time = datetime.now()
    
    print_header()
    
    # 确认操作
    if not confirm_operation():
        print("\n操作已取消")
        return
    
    print("\n" + "═" * 70)
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 70)
    
    # 执行导入
    if not run_import():
        print("\n✗ 数据导入失败，操作终止")
        return
    
    # 执行更新
    if not run_update():
        print("\n✗ 配置更新失败，但数据已导入")
        print("  可以手动运行: python update_app_config.py")
        return
    
    # 完成
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "═" * 70)
    print("✓ 所有操作完成！")
    print("═" * 70)
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {duration:.2f} 秒")
    print("═" * 70)
    
    print("\n下一步操作：")
    print("  1. 重启应用服务器")
    print("     方式1: 双击 start.bat")
    print("     方式2: cd backend && python app.py")
    print()
    print("  2. 访问系统")
    print("     浏览器打开: http://localhost:5000")
    print()
    print("  3. 验证数据")
    print("     在页面中选择不同股性分组，查看是否有20支股票")
    print()
    
    print("备份文件：")
    print("  - backend/app.py.backup (原配置文件)")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
    except Exception as e:
        print(f"\n\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()

