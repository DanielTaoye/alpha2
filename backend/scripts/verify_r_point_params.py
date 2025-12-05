"""
验证R点插件参数调整是否生效
检查具体案例：思瑞浦 2024-06-24 和 蓝色光标 2024-08-20
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from domain.services.config_service import get_config_service
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl


def main():
    print("=" * 80)
    print("R点插件参数调整验证")
    print("=" * 80)
    
    # 1. 验证当前配置
    config_service = get_config_service()
    pressure_threshold = config_service.get_pressure_stagnation_distance_threshold()
    gain_threshold = config_service.get_high_position_gain_threshold()
    
    print(f"\n✅ 当前配置参数：")
    print(f"   - 临近压力位滞涨距离阈值: {pressure_threshold}%")
    print(f"   - 高位发R涨幅阈值: {gain_threshold}%")
    
    # 2. 初始化服务
    r_plugin_service = RPointPluginService()
    daily_repo = DailyRepositoryImpl()
    daily_chance_repo = DailyChanceRepositoryImpl()
    
    # 测试案例
    test_cases = [
        {
            'stock_code': 'SH688508',  # 思瑞浦
            'stock_name': '思瑞浦',
            'date': '2024-06-24'
        },
        {
            'stock_code': 'SZ300058',  # 蓝色光标
            'stock_name': '蓝色光标',
            'date': '2024-08-20'  # 假设是2024年
        }
    ]
    
    for case in test_cases:
        print("\n" + "=" * 80)
        print(f"📊 案例：{case['stock_name']} ({case['stock_code']}) - {case['date']}")
        print("=" * 80)
        
        stock_code = case['stock_code']
        check_date = case['date']
        
        # 查询当日数据
        daily_data = daily_repo.find_by_date(stock_code, check_date)
        daily_chance = daily_chance_repo.find_by_stock_and_date(stock_code, check_date)
        
        if not daily_data:
            print(f"❌ 未找到 {case['stock_name']} 在 {check_date} 的K线数据")
            continue
        
        if not daily_chance:
            print(f"❌ 未找到 {case['stock_name']} 在 {check_date} 的daily_chance数据")
            continue
        
        print(f"\n📈 K线数据：")
        print(f"   开盘: {daily_data.open:.2f}")
        print(f"   收盘: {daily_data.close:.2f}")
        print(f"   最高: {daily_data.high:.2f}")
        print(f"   最低: {daily_data.low:.2f}")
        print(f"   昨收: {daily_data.pre_close:.2f}")
        
        print(f"\n📊 Daily Chance数据：")
        print(f"   成交量类型: {daily_chance.volume_type}")
        print(f"   股性: {daily_chance.stock_nature}")
        
        # 检查压力位相关数据
        if daily_chance.pressure_price:
            pressure_price_actual = daily_chance.pressure_price / 100.0
            distance_pct = (pressure_price_actual - daily_data.close) / daily_data.close * 100
            print(f"   压力位: {pressure_price_actual:.2f}")
            print(f"   股价距压力位: {distance_pct:.2f}%")
            
            # 判断是否在阈值范围内
            if 0 < distance_pct < pressure_threshold:
                print(f"   ✅ 在当前阈值范围内 (0% < {distance_pct:.2f}% < {pressure_threshold}%)")
            else:
                print(f"   ❌ 不在当前阈值范围内 (需要 0% < 距离 < {pressure_threshold}%)")
        else:
            print(f"   压力位: 无数据")
        
        if daily_chance.support_price:
            support_price_actual = daily_chance.support_price / 100.0
            print(f"   支撑位: {support_price_actual:.2f}")
        else:
            print(f"   支撑位: 无数据")
        
        if daily_chance.day_win_ratio_score is not None:
            print(f"   日线赔率得分: {daily_chance.day_win_ratio_score:.1f}")
        
        # 初始化缓存（查询前后30天数据）
        from datetime import datetime, timedelta
        date_obj = datetime.strptime(check_date, '%Y-%m-%d')
        start_date = (date_obj - timedelta(days=60)).strftime('%Y-%m-%d')
        end_date = (date_obj + timedelta(days=30)).strftime('%Y-%m-%d')
        
        print(f"\n🔍 初始化R点插件缓存 ({start_date} 至 {end_date})...")
        r_plugin_service.init_cache(stock_code, start_date, end_date)
        
        # 检查R点
        print(f"\n🎯 检查R点触发情况...")
        date_obj = datetime.strptime(check_date, '%Y-%m-%d')
        is_r, triggered_plugins = r_plugin_service.check_r_point(
            stock_code,
            date_obj,
            c_point_date=None,  # 简化测试，不传C点日期
            ma_data=None,
            macd_data=None,
            current_index=None,
            kline_data=None
        )
        
        if is_r:
            print(f"\n✅ 触发R点！")
            for plugin in triggered_plugins:
                print(f"\n   插件: {plugin.plugin_name}")
                print(f"   原因: {plugin.reason}")
        else:
            print(f"\n❌ 未触发R点")
            if triggered_plugins:
                print(f"\n   检查的插件:")
                for plugin in triggered_plugins:
                    print(f"   - {plugin.plugin_name}: {'触发' if plugin.triggered else '未触发'}")
        
        # 清空缓存
        r_plugin_service.clear_cache()
    
    print("\n" + "=" * 80)
    print("验证完成！")
    print("=" * 80)
    
    # 对比说明
    print(f"\n💡 参数调整影响说明：")
    print(f"   1. 临近压力位滞涨距离阈值: 10% → {pressure_threshold}%")
    print(f"      - 原来：股价距压力位在0%-10%范围内才触发")
    print(f"      - 现在：股价距压力位在0%-{pressure_threshold}%范围内就触发")
    print(f"      - 影响：触发范围扩大{pressure_threshold - 10}%，更容易触发")
    print(f"")
    print(f"   2. 高位发R涨幅阈值: 8% → {gain_threshold}%")
    print(f"      - 原来：前20日最低价涨幅>8%才触发")
    print(f"      - 现在：前20日最低价涨幅>{gain_threshold}%才触发")
    print(f"      - 影响：要求涨幅更大才触发，更严格")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

