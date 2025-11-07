#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
更新 backend/app.py 中的 STOCK_GROUPS 配置
将每个股性分组从5支扩展到20支
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

# 新的股票分组配置（20支每组）
NEW_STOCK_GROUPS = """# 股票分组配置
STOCK_GROUPS = {
    '波段': [
        {'name': '国投智能', 'code': 'SZ300188', 'table': 'basic_data_sz300188'},
        {'name': '海兴电力', 'code': 'SH603556', 'table': 'basic_data_sh603556'},
        {'name': '沃尔核材', 'code': 'SZ002130', 'table': 'basic_data_sz002130'},
        {'name': '歌华有线', 'code': 'SH600037', 'table': 'basic_data_sh600037'},
        {'name': '中集车辆', 'code': 'SZ301039', 'table': 'basic_data_sz301039'},
        {'name': '蓝色光标', 'code': 'SZ300058', 'table': 'basic_data_sz300058'},
        {'name': '迪普科技', 'code': 'SZ300768', 'table': 'basic_data_sz300768'},
        {'name': '思瑞浦', 'code': 'SH688536', 'table': 'basic_data_sh688536'},
        {'name': '时代新材', 'code': 'SH600458', 'table': 'basic_data_sh600458'},
        {'name': '东华软件', 'code': 'SZ002065', 'table': 'basic_data_sz002065'},
        {'name': '福蓉科技', 'code': 'SH603327', 'table': 'basic_data_sh603327'},
        {'name': '筑博设计', 'code': 'SZ300564', 'table': 'basic_data_sz300564'},
        {'name': '杭叉集团', 'code': 'SH603298', 'table': 'basic_data_sh603298'},
        {'name': '维信诺', 'code': 'SZ002387', 'table': 'basic_data_sz002387'},
        {'name': '康美药业', 'code': 'SH600518', 'table': 'basic_data_sh600518'},
        {'name': '广汇能源', 'code': 'SH600256', 'table': 'basic_data_sh600256'},
        {'name': '科沃斯', 'code': 'SH603486', 'table': 'basic_data_sh603486'},
        {'name': '高能环境', 'code': 'SH603588', 'table': 'basic_data_sh603588'},
        {'name': '北新建材', 'code': 'SZ000786', 'table': 'basic_data_sz000786'},
        {'name': '安通控股', 'code': 'SH600179', 'table': 'basic_data_sh600179'}
    ],
    '短线': [
        {'name': '白云机场', 'code': 'SH600004', 'table': 'basic_data_sh600004'},
        {'name': '金雷股份', 'code': 'SZ300443', 'table': 'basic_data_sz300443'},
        {'name': '南京化纤', 'code': 'SH600889', 'table': 'basic_data_sh600889'},
        {'name': '慧智微-U', 'code': 'SH688512', 'table': 'basic_data_sh688512'},
        {'name': '锴威特', 'code': 'SH688693', 'table': 'basic_data_sh688693'},
        {'name': '新疆天业', 'code': 'SH600075', 'table': 'basic_data_sh600075'},
        {'name': '物产金轮', 'code': 'SZ002722', 'table': 'basic_data_sz002722'},
        {'name': '中巨芯-U', 'code': 'SH688549', 'table': 'basic_data_sh688549'},
        {'name': '美湖股份', 'code': 'SH603319', 'table': 'basic_data_sh603319'},
        {'name': '依米康', 'code': 'SZ300249', 'table': 'basic_data_sz300249'},
        {'name': '中化装备', 'code': 'SH600579', 'table': 'basic_data_sh600579'},
        {'name': '科锐国际', 'code': 'SZ300662', 'table': 'basic_data_sz300662'},
        {'name': '三晖电气', 'code': 'SZ002857', 'table': 'basic_data_sz002857'},
        {'name': '易尚退', 'code': 'SZ002751', 'table': 'basic_data_sz002751'},
        {'name': '长青科技', 'code': 'SZ001324', 'table': 'basic_data_sz001324'},
        {'name': '菲菱科思', 'code': 'SZ301191', 'table': 'basic_data_sz301191'},
        {'name': '运达股份', 'code': 'SZ300772', 'table': 'basic_data_sz300772'},
        {'name': '上纬新材', 'code': 'SH688585', 'table': 'basic_data_sh688585'},
        {'name': '开创电气', 'code': 'SZ301448', 'table': 'basic_data_sz301448'},
        {'name': '康希通信', 'code': 'SH688653', 'table': 'basic_data_sh688653'}
    ],
    '中长线': [
        {'name': '立讯精密', 'code': 'SZ002475', 'table': 'basic_data_sz002475'},
        {'name': '宁德时代', 'code': 'SZ300750', 'table': 'basic_data_sz300750'},
        {'name': '农业银行', 'code': 'SH601288', 'table': 'basic_data_sh601288'},
        {'name': '中国石油', 'code': 'SH601857', 'table': 'basic_data_sh601857'},
        {'name': '紫金矿业', 'code': 'SH601899', 'table': 'basic_data_sh601899'},
        {'name': '传音控股', 'code': 'SH688036', 'table': 'basic_data_sh688036'},
        {'name': '常熟银行', 'code': 'SH601128', 'table': 'basic_data_sh601128'},
        {'name': '潍柴动力', 'code': 'SZ000338', 'table': 'basic_data_sz000338'},
        {'name': '海螺水泥', 'code': 'SH600585', 'table': 'basic_data_sh600585'},
        {'name': '民生银行', 'code': 'SH600016', 'table': 'basic_data_sh600016'},
        {'name': '华域汽车', 'code': 'SH600741', 'table': 'basic_data_sh600741'},
        {'name': '申万宏源', 'code': 'SZ000166', 'table': 'basic_data_sz000166'},
        {'name': '陕西煤业', 'code': 'SH601225', 'table': 'basic_data_sh601225'},
        {'name': '泸州老窖', 'code': 'SZ000568', 'table': 'basic_data_sz000568'},
        {'name': '江阴银行', 'code': 'SZ002807', 'table': 'basic_data_sz002807'},
        {'name': '中微公司', 'code': 'SH688012', 'table': 'basic_data_sh688012'},
        {'name': '春秋航空', 'code': 'SH601021', 'table': 'basic_data_sh601021'},
        {'name': '光启技术', 'code': 'SZ002625', 'table': 'basic_data_sz002625'},
        {'name': '宇通客车', 'code': 'SH600066', 'table': 'basic_data_sh600066'},
        {'name': '中远海控', 'code': 'SH601919', 'table': 'basic_data_sh601919'}
    ]
}"""


def backup_file(file_path):
    """备份原文件"""
    backup_path = file_path + '.backup'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ 已备份原文件到: {backup_path}")
        return True
    except Exception as e:
        print(f"✗ 备份文件失败: {e}")
        return False


def update_app_config():
    """更新 backend/app.py 配置"""
    app_file = 'backend/app.py'
    
    if not os.path.exists(app_file):
        print(f"✗ 文件不存在: {app_file}")
        return False
    
    print("=" * 70)
    print("更新 backend/app.py 配置")
    print("=" * 70)
    
    # 备份原文件
    print("\n1. 备份原文件...")
    if not backup_file(app_file):
        return False
    
    # 读取文件
    print("\n2. 读取配置文件...")
    try:
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
        print("✓ 配置文件读取成功")
    except Exception as e:
        print(f"✗ 读取配置文件失败: {e}")
        return False
    
    # 查找并替换 STOCK_GROUPS
    print("\n3. 更新股票分组配置...")
    try:
        # 找到 STOCK_GROUPS 的开始和结束位置
        start_marker = "# 股票分组配置\nSTOCK_GROUPS = {"
        end_marker = "}\n\n# 周期类型映射"
        
        start_pos = content.find(start_marker)
        if start_pos == -1:
            print("✗ 未找到 STOCK_GROUPS 配置")
            return False
        
        # 找到配置块的结束位置（找到匹配的 }）
        brace_count = 0
        end_pos = start_pos + len(start_marker)
        
        for i in range(end_pos, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                if brace_count == 0:
                    end_pos = i + 1
                    break
                else:
                    brace_count -= 1
        
        # 替换配置
        new_content = content[:start_pos] + NEW_STOCK_GROUPS + "\n\n" + content[end_pos:]
        
        # 写入文件
        with open(app_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✓ 股票分组配置更新成功")
        print("  - 波段策略: 5支 → 20支")
        print("  - 短线策略: 5支 → 20支")
        print("  - 中长线策略: 5支 → 20支")
        
    except Exception as e:
        print(f"✗ 更新配置失败: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("✓ 配置更新完成！")
    print("=" * 70)
    print("\n下一步：")
    print("1. 检查更新后的配置: backend/app.py")
    print("2. 重启应用服务器")
    print("3. 访问 http://localhost:5000 查看新股票")
    
    return True


if __name__ == '__main__':
    if update_app_config():
        print("\n✓ 所有操作完成！")
    else:
        print("\n✗ 更新失败，请检查错误信息")

