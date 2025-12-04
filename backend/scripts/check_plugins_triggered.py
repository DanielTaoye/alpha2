"""检查12月3日哪些股票触发了插件"""
import sys
import os
from typing import List, Dict
import requests
from datetime import datetime

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from domain.models.stock import StockGroups
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# API基础URL
API_BASE_URL = "http://localhost:5000"


def get_all_stocks() -> List[Dict]:
    """获取所有股票信息"""
    stock_groups = StockGroups()
    all_groups = stock_groups.get_all_groups()
    
    stocks = []
    for group_name, stock_list in all_groups.items():
        for stock in stock_list:
            stocks.append({
                'code': stock.code,
                'name': stock.name,
                'table': stock.table_name,
                'nature': group_name
            })
    
    logger.info(f"获取到 {len(stocks)} 支股票")
    return stocks


def check_stock_plugins(stock_code: str, stock_name: str, table_name: str) -> Dict:
    """
    检查指定股票是否触发了插件
    
    Returns:
        {
            'has_plugins': bool,
            'strategy1_plugins': List,
            'r_point_plugins': List,
            'strategy1_score': float,
            'strategy1_base_score': float,
            'date': str
        }
    """
    try:
        # 调用 latest_cr_points 接口
        response = requests.post(
            f"{API_BASE_URL}/api/latest_cr_points",
            json={
                'stockCode': stock_code,
                'tableName': table_name
            },
            timeout=30
        )
        
        if response.status_code != 200:
            logger.warning(f"  [{stock_code}] HTTP状态码: {response.status_code}")
            return {'has_plugins': False, 'error': f"HTTP {response.status_code}"}
        
        result = response.json()
        
        if result.get('code') != 200:
            logger.warning(f"  [{stock_code}] API返回错误: {result.get('message')}")
            return {'has_plugins': False, 'error': result.get('message')}
        
        data = result.get('data', {})
        
        # 提取插件信息
        strategy1 = data.get('strategy1', {})
        r_point = data.get('r_point', {})
        
        strategy1_plugins = strategy1.get('plugins', [])
        r_point_plugins = r_point.get('plugins', [])
        
        has_plugins = len(strategy1_plugins) > 0 or len(r_point_plugins) > 0
        
        return {
            'has_plugins': has_plugins,
            'strategy1_plugins': strategy1_plugins,
            'r_point_plugins': r_point_plugins,
            'strategy1_score': strategy1.get('score', 0),
            'strategy1_base_score': strategy1.get('base_score', 0),
            'strategy1_is_c_point': strategy1.get('is_c_point', False),
            'strategy2_score': data.get('strategy2', {}).get('score', 0),
            'strategy2_is_c_point': data.get('strategy2', {}).get('is_c_point', False),
            'r_point_is_triggered': r_point.get('is_r_point', False),
            'date': data.get('date', ''),
            'volume_type': data.get('volume_type', '')
        }
        
    except requests.exceptions.Timeout:
        logger.error(f"  [{stock_code}] 请求超时")
        return {'has_plugins': False, 'error': '请求超时'}
    except Exception as e:
        logger.error(f"  [{stock_code}] 检查失败: {e}")
        return {'has_plugins': False, 'error': str(e)}


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info(f"开始检查12月3日触发插件的股票 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # 获取所有股票
    stocks = get_all_stocks()
    
    if not stocks:
        logger.error("❌ 未获取到任何股票")
        return
    
    logger.info(f"开始检查 {len(stocks)} 支股票...")
    logger.info("")
    
    # 统计结果
    triggered_stocks = []
    success_count = 0
    error_count = 0
    
    # 遍历所有股票
    for i, stock in enumerate(stocks, 1):
        stock_code = stock['code']
        stock_name = stock['name']
        table_name = stock['table']
        nature = stock['nature']
        
        logger.info(f"[{i}/{len(stocks)}] 检查 {stock_code} {stock_name} ({nature})...")
        
        result = check_stock_plugins(stock_code, stock_name, table_name)
        
        if result.get('error'):
            error_count += 1
            logger.warning(f"  ❌ 失败: {result['error']}")
        else:
            success_count += 1
            
            if result['has_plugins']:
                triggered_stocks.append({
                    'code': stock_code,
                    'name': stock_name,
                    'nature': nature,
                    'result': result
                })
                
                logger.info(f"  ✅ 触发插件!")
                
                # 输出详细信息
                if result['strategy1_plugins']:
                    logger.info(f"     【策略1插件】")
                    for plugin in result['strategy1_plugins']:
                        logger.info(f"       - {plugin.get('plugin_name', 'Unknown')}: {plugin.get('reason', '')}")
                    logger.info(f"       基础分: {result['strategy1_base_score']:.2f}, 最终分: {result['strategy1_score']:.2f}")
                
                if result['r_point_plugins']:
                    logger.info(f"     【R点插件】")
                    for plugin in result['r_point_plugins']:
                        logger.info(f"       - {plugin.get('plugin_name', 'Unknown')}: {plugin.get('reason', '')}")
                
                logger.info(f"     日期: {result.get('date', 'N/A')}, 成交量类型: {result.get('volume_type', 'N/A')}")
            else:
                logger.info(f"  ⚪ 未触发插件")
    
    # 输出汇总报告
    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 检查完成 - 汇总报告")
    logger.info("=" * 80)
    logger.info(f"总股票数: {len(stocks)}")
    logger.info(f"成功检查: {success_count}")
    logger.info(f"失败数量: {error_count}")
    logger.info(f"触发插件: {len(triggered_stocks)}")
    logger.info("")
    
    if triggered_stocks:
        logger.info("🔥 触发插件的股票详细列表:")
        logger.info("-" * 80)
        
        for stock in triggered_stocks:
            code = stock['code']
            name = stock['name']
            nature = stock['nature']
            result = stock['result']
            
            logger.info(f"\n📌 {code} - {name} ({nature})")
            logger.info(f"   日期: {result.get('date', 'N/A')}")
            logger.info(f"   成交量类型: {result.get('volume_type', 'N/A')}")
            
            if result['strategy1_plugins']:
                logger.info(f"   【策略1】 基础分: {result['strategy1_base_score']:.2f} → 最终分: {result['strategy1_score']:.2f}")
                logger.info(f"            触发C点: {'✅' if result['strategy1_is_c_point'] else '❌'}")
                for plugin in result['strategy1_plugins']:
                    logger.info(f"            • {plugin.get('plugin_name', 'Unknown')}")
                    logger.info(f"              {plugin.get('reason', '')}")
            
            if result['r_point_plugins']:
                logger.info(f"   【R点】 触发: {'✅' if result['r_point_is_triggered'] else '❌'}")
                for plugin in result['r_point_plugins']:
                    logger.info(f"            • {plugin.get('plugin_name', 'Unknown')}")
                    logger.info(f"              {plugin.get('reason', '')}")
        
        logger.info("")
        logger.info("-" * 80)
        
        # 输出简洁列表
        logger.info("\n📋 触发插件股票列表（简洁版）:")
        for stock in triggered_stocks:
            code = stock['code']
            name = stock['name']
            result = stock['result']
            
            plugin_types = []
            if result['strategy1_plugins']:
                plugin_types.append(f"策略1({len(result['strategy1_plugins'])}个)")
            if result['r_point_plugins']:
                plugin_types.append(f"R点({len(result['r_point_plugins'])}个)")
            
            logger.info(f"  • {code} {name} - {', '.join(plugin_types)}")
    else:
        logger.info("⚪ 没有股票触发插件")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"检查完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n用户中断执行")
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)

