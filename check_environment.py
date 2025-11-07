#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
环境检查脚本
在导入数据前检查所有前置条件
"""

import sys
import os

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


def check_python_version():
    """检查Python版本"""
    print("1. 检查Python版本...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 6:
        print(f"   ✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ✗ Python版本过低: {version.major}.{version.minor}.{version.micro}")
        print("   需要Python 3.6或更高版本")
        return False


def check_pymysql():
    """检查pymysql库"""
    print("\n2. 检查pymysql库...")
    try:
        import pymysql
        print(f"   ✓ pymysql已安装")
        return True
    except ImportError:
        print("   ✗ pymysql未安装")
        print("   请运行: pip install pymysql")
        return False


def check_prod_db():
    """检查生产环境数据库连接"""
    print("\n3. 检查生产环境数据库连接...")
    try:
        import pymysql
        
        config = {
            'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
            'port': 21648,
            'user': 'root',
            'password': 'MrEPYZus7myr',
            'database': 'stock',
            'charset': 'utf8mb4',
            'connect_timeout': 10
        }
        
        conn = pymysql.connect(**config)
        
        # 检查basic_stock表
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM basic_stock")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        print(f"   ✓ 连接成功")
        print(f"   ✓ basic_stock表有 {count} 条记录")
        return True
        
    except pymysql.err.OperationalError as e:
        print(f"   ✗ 连接失败: {e}")
        print("   可能原因：")
        print("     - 网络连接问题")
        print("     - 数据库未启动")
        print("     - IP未加入白名单")
        return False
    except Exception as e:
        print(f"   ✗ 检查失败: {e}")
        return False


def check_local_db():
    """检查本地数据库连接"""
    print("\n4. 检查本地数据库连接...")
    try:
        import pymysql
        
        config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '1234',
            'database': 'stock',
            'charset': 'utf8mb4',
            'connect_timeout': 5
        }
        
        conn = pymysql.connect(**config)
        
        # 检查basic_stock表
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM basic_stock")
            count = cursor.fetchone()[0]
            print(f"   ✓ 连接成功")
            print(f"   ✓ basic_stock表有 {count} 条记录")
            has_table = True
        except:
            print(f"   ✓ 连接成功")
            print(f"   ⚠ basic_stock表不存在（将在导入时创建）")
            has_table = False
        
        cursor.close()
        conn.close()
        return True
        
    except pymysql.err.OperationalError as e:
        error_code = e.args[0] if e.args else 0
        if error_code == 1049:
            print(f"   ✗ 数据库 'stock' 不存在")
            print("   请先创建数据库:")
            print("     mysql -u root -p -e \"CREATE DATABASE stock CHARACTER SET utf8mb4;\"")
        elif error_code == 1045:
            print(f"   ✗ 用户名或密码错误")
            print("   请修改 import_stocks_from_prod.py 中的 LOCAL_DB_CONFIG")
        elif error_code == 2003:
            print(f"   ✗ 无法连接到MySQL服务器")
            print("   请确认MySQL服务正在运行")
        else:
            print(f"   ✗ 连接失败: {e}")
        return False
    except Exception as e:
        print(f"   ✗ 检查失败: {e}")
        return False


def check_files():
    """检查必需文件"""
    print("\n5. 检查必需文件...")
    
    required_files = [
        'import_stocks_from_prod.py',
        'update_app_config.py',
        'import_and_update.py',
        'backend/app.py'
    ]
    
    all_exists = True
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✓ {file}")
        else:
            print(f"   ✗ {file} 不存在")
            all_exists = False
    
    return all_exists


def check_disk_space():
    """检查磁盘空间"""
    print("\n6. 检查磁盘空间...")
    try:
        import shutil
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024**3)
        
        if free_gb >= 1:
            print(f"   ✓ 可用空间: {free_gb:.2f} GB")
            return True
        else:
            print(f"   ⚠ 可用空间不足: {free_gb:.2f} GB")
            print("   建议至少保留1GB空间")
            return False
    except Exception as e:
        print(f"   ⚠ 无法检查磁盘空间: {e}")
        return True


def main():
    """主函数"""
    print("=" * 70)
    print("环境检查")
    print("=" * 70)
    
    results = []
    
    # 执行检查
    results.append(("Python版本", check_python_version()))
    results.append(("pymysql库", check_pymysql()))
    results.append(("生产环境数据库", check_prod_db()))
    results.append(("本地数据库", check_local_db()))
    results.append(("必需文件", check_files()))
    results.append(("磁盘空间", check_disk_space()))
    
    # 输出结果
    print("\n" + "=" * 70)
    print("检查结果汇总")
    print("=" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name:20s} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n✓ 所有检查通过！可以开始导入数据")
        print("\n运行以下命令开始导入：")
        print("  python import_and_update.py")
        print("\n或双击运行：")
        print("  导入股票数据.bat")
    else:
        print("\n✗ 部分检查未通过，请先解决上述问题")
        print("\n常见问题解决：")
        print("  1. 安装pymysql: pip install pymysql")
        print("  2. 创建数据库: mysql -u root -p -e \"CREATE DATABASE stock;\"")
        print("  3. 检查MySQL服务是否运行")
        print("  4. 检查网络连接")
        print("  5. 添加本机IP到腾讯云数据库白名单")
    
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n检查被用户中断")
    except Exception as e:
        print(f"\n\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()

