"""验证日K数据查询修复 - 确保查询的是日K而不是其他周期"""
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from infrastructure.persistence.database import DatabaseConnection
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
import pymysql.cursors


def check_raw_data(stock_code: str, date_str: str):
    """直接查看数据库中该日期的所有周期数据"""
    try:
        table_name = f"basic_data_{stock_code.lower()}"
        
        with DatabaseConnection.get_connection_context() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 查看该日期所有周期的数据
            query = f"""
                SELECT peroid_type, shi_jian, kai_pan_jia, shou_pan_jia, zui_gao_jia, zui_di_jia
                FROM {table_name}
                WHERE DATE(shi_jian) = %s
                ORDER BY peroid_type
            """
            
            cursor.execute(query, (date_str,))
            results = cursor.fetchall()
            
            print(f"\n{'='*80}")
            print(f"数据库原始数据: {stock_code} {date_str}")
            print(f"{'='*80}")
            
            if not results:
                print("❌ 未找到数据")
                return
            
            for row in results:
                print(f"\n周期: {row['peroid_type']}")
                print(f"  时间: {row['shi_jian']}")
                print(f"  开盘价: {row['kai_pan_jia']}")
                print(f"  收盘价: {row['shou_pan_jia']}")
                print(f"  最高价: {row['zui_gao_jia']}")
                print(f"  最低价: {row['zui_di_jia']}")
    
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()


def check_repository_query(stock_code: str, date_str: str):
    """使用修复后的 DailyRepositoryImpl 查询"""
    try:
        repo = DailyRepositoryImpl()
        
        print(f"\n{'='*80}")
        print(f"DailyRepositoryImpl 查询结果: {stock_code} {date_str}")
        print(f"{'='*80}")
        
        daily_data = repo.find_by_date(stock_code, date_str)
        
        if not daily_data:
            print("❌ 未找到数据")
            return
        
        print(f"\n✅ 查询成功（应该是日K数据）:")
        print(f"  日期: {daily_data.date}")
        print(f"  开盘价: {daily_data.open}")
        print(f"  收盘价: {daily_data.close}")
        print(f"  最高价: {daily_data.high}")
        print(f"  最低价: {daily_data.low}")
        print(f"  成交量: {daily_data.volume}")
        print(f"  昨收价: {daily_data.pre_close:.2f}" if daily_data.pre_close else "  昨收价: N/A")
        
        # 判断阴阳线
        if daily_data.close < daily_data.open:
            print(f"  📉 阴线 (收盘 {daily_data.close} < 开盘 {daily_data.open})")
        elif daily_data.close > daily_data.open:
            print(f"  📈 阳线 (收盘 {daily_data.close} > 开盘 {daily_data.open})")
        else:
            print(f"  ➖ 十字星 (收盘 = 开盘 = {daily_data.close})")
    
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("\n" + "="*80)
    print("验证日K数据查询修复")
    print("="*80)
    
    # 测试用例1: 国投智能 2024-10-31（用户报告的问题）
    print("\n" + "="*80)
    print("测试用例 1: 国投智能 (SZ300188) 2024-10-31")
    print("预期: 日K开盘价 15.9，收盘价 16.51（阳线）")
    print("="*80)
    
    check_raw_data("SZ300188", "2024-10-31")
    check_repository_query("SZ300188", "2024-10-31")
    
    # 测试用例2: 多几个日期
    test_cases = [
        ("SZ300188", "2024-11-01", "国投智能 2024-11-01"),
        ("SH600000", "2024-11-24", "浦发银行 2024-11-24"),
    ]
    
    for stock_code, date_str, desc in test_cases:
        print("\n" + "="*80)
        print(f"测试用例: {desc}")
        print("="*80)
        
        check_raw_data(stock_code, date_str)
        check_repository_query(stock_code, date_str)
    
    print("\n" + "="*80)
    print("验证完成！")
    print("="*80)
    print("\n说明:")
    print("- 如果数据库中有多个周期（30min, 1day, week, month）")
    print("- DailyRepositoryImpl 应该只返回 peroid_type='1day' 的数据")
    print("- 确保插件使用的是正确的日K数据，而不是周K或月K")
    print("="*80)


if __name__ == '__main__':
    main()

