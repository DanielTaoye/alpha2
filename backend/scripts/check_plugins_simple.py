"""检查12月3日哪些股票触发了插件（精简版）"""
import sys
import os
import requests
from datetime import datetime

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from domain.models.stock import StockGroups

# API基础URL
API_BASE_URL = "http://localhost:5000"


def get_all_stocks():
    """获取所有股票信息"""
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    stocks = []
    for group_name, stock_list in all_groups.items():
        for stock in stock_list:
            stocks.append({
                'code': stock.code,
                'name': stock.name,
                'table': stock.table_name
            })
    return stocks


def check_stock_plugins(stock_code, table_name):
    """检查股票是否触发插件"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/latest_cr_points",
            json={'stockCode': stock_code, 'tableName': table_name},
            timeout=30
        )
        
        if response.status_code != 200:
            return None
        
        result = response.json()
        if result.get('code') != 200:
            return None
        
        data = result.get('data', {})
        strategy1_plugins = data.get('strategy1', {}).get('plugins', [])
        r_point_plugins = data.get('r_point', {}).get('plugins', [])
        
        if strategy1_plugins or r_point_plugins:
            return {
                'date': data.get('date', ''),
                'volume_type': data.get('volume_type', ''),
                'strategy1_plugins': strategy1_plugins,
                'r_point_plugins': r_point_plugins,
                'strategy1_score': data.get('strategy1', {}).get('score', 0),
                'strategy1_base_score': data.get('strategy1', {}).get('base_score', 0),
                'is_c_point': data.get('strategy1', {}).get('is_c_point', False),
                'is_r_point': data.get('r_point', {}).get('is_r_point', False)
            }
        return None
        
    except Exception:
        return None


def main():
    """主函数"""
    print("=" * 80)
    print(f"检查12月3日触发插件的股票 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    stocks = get_all_stocks()
    print(f"正在检查 {len(stocks)} 支股票...")
    print()
    
    triggered_stocks = []
    
    for i, stock in enumerate(stocks, 1):
        print(f"\r进度: [{i}/{len(stocks)}] {stock['code']} {stock['name']}", end='', flush=True)
        
        result = check_stock_plugins(stock['code'], stock['table'])
        if result:
            triggered_stocks.append({
                'code': stock['code'],
                'name': stock['name'],
                'result': result
            })
    
    print("\r" + " " * 100)  # 清空进度行
    print("\r", end='')
    
    # 输出结果
    print()
    print("=" * 80)
    print(f"🎯 检查完成，共发现 {len(triggered_stocks)} 支股票触发插件")
    print("=" * 80)
    print()
    
    if triggered_stocks:
        # 按插件数量排序
        triggered_stocks.sort(key=lambda x: len(x['result']['strategy1_plugins']) + len(x['result']['r_point_plugins']), reverse=True)
        
        for stock in triggered_stocks:
            code = stock['code']
            name = stock['name']
            result = stock['result']
            
            s1_plugins = result['strategy1_plugins']
            r_plugins = result['r_point_plugins']
            
            plugin_count = len(s1_plugins) + len(r_plugins)
            
            print(f"📌 {code} - {name}")
            print(f"   日期: {result['date']}  成交量: {result['volume_type']}")
            
            if s1_plugins:
                c_mark = "✅" if result['is_c_point'] else "❌"
                print(f"   策略1 {c_mark}: {result['strategy1_base_score']:.1f} → {result['strategy1_score']:.1f}")
                for p in s1_plugins:
                    print(f"     • {p.get('plugin_name', 'Unknown')}")
            
            if r_plugins:
                r_mark = "✅" if result['is_r_point'] else "❌"
                print(f"   R点 {r_mark}:")
                for p in r_plugins:
                    print(f"     • {p.get('plugin_name', 'Unknown')}")
            
            print()
        
        print("-" * 80)
        print("📋 触发插件股票列表（复制用）:")
        for stock in triggered_stocks:
            s1_count = len(stock['result']['strategy1_plugins'])
            r_count = len(stock['result']['r_point_plugins'])
            marks = []
            if s1_count > 0:
                marks.append(f"C×{s1_count}")
            if r_count > 0:
                marks.append(f"R×{r_count}")
            print(f"{stock['code']} {stock['name']} - {', '.join(marks)}")
    else:
        print("⚪ 没有股票触发插件")
    
    print()
    print("=" * 80)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断执行")
    except Exception as e:
        print(f"\n\n❌ 执行失败: {e}")

