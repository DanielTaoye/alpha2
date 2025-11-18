"""专门测试乖离率偏离插件的调试脚本"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from domain.services.r_point_plugin_service import RPointPluginService
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from infrastructure.logging.logger import get_logger
import logging

# 设置日志级别为DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(message)s'
)
logger = get_logger(__name__)


def test_deviation_plugin(stock_code: str, start_date_str: str, end_date_str: str):
    """
    专门测试乖离率偏离插件
    """
    print("="*100)
    print(f"测试乖离率偏离插件: {stock_code} 从 {start_date_str} 到 {end_date_str}")
    print("="*100)
    
    try:
        daily_repo = DailyRepositoryImpl()
        daily_chance_repo = DailyChanceRepositoryImpl()
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # 往前多取30天
        query_start = (start_date - timedelta(days=30)).strftime('%Y-%m-%d')
        query_end = end_date.strftime('%Y-%m-%d')
        
        # 只查询日线数据
        daily_data_list = []
        all_data = daily_repo.find_by_date_range(stock_code, query_start, query_end)
        for d in all_data:
            # 过滤掉时间不是00:00:00的数据（分钟数据）
            if d.date.hour == 0 and d.date.minute == 0:
                daily_data_list.append(d)
        
        print(f"查询到 {len(daily_data_list)} 条日线数据")
        
        if not daily_data_list:
            print(f"未找到股票 {stock_code} 的日线数据")
            return
        
        # 筛选测试日期范围内的数据
        test_dates = []
        for daily in daily_data_list:
            if start_date.date() <= daily.date.date() <= end_date.date():
                test_dates.append(daily.date)
        
        print(f"测试日期范围内有 {len(test_dates)} 个交易日")
        
        # 初始化R点服务
        r_service = RPointPluginService()
        r_service.init_cache(stock_code, query_start, query_end)
        
        print(f"缓存已初始化: daily={len(r_service._daily_cache)}条, daily_chance={len(r_service._daily_chance_cache)}条\n")
        
        # 主板还是非主板
        is_main_board = stock_code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001'))
        board_type = "主板" if is_main_board else "创业板/科创板"
        print(f"股票类型: {board_type}")
        print(f"涨停阈值: {'9.9%' if is_main_board else '19.8%'}")
        print(f"前3日涨幅阈值: {'15%' if is_main_board else '20%'}")
        print(f"前5日涨幅阈值: {'20%' if is_main_board else '25%'}\n")
        
        # 检查每个交易日
        print("-"*100)
        print("开始检测...")
        print("-"*100)
        
        for test_date in test_dates:
            date_str = test_date.strftime('%Y-%m-%d')
            
            # 检查缓存数据
            if date_str not in r_service._daily_cache:
                continue
            
            if date_str not in r_service._daily_chance_cache:
                continue
            
            current_data = r_service._daily_cache[date_str]
            current_chance = r_service._daily_chance_cache[date_str]
            
            # 获取前20日数据
            prev_dates = r_service._get_previous_trading_dates_from_cache(date_str)
            if len(prev_dates) < 20:
                continue
            
            # 计算涨跌幅
            change_pcts = []
            for i in range(min(20, len(prev_dates))):
                prev_date = prev_dates[i]
                if prev_date not in r_service._daily_cache:
                    break
                data = r_service._daily_cache[prev_date]
                if data.pre_close and data.pre_close > 0:
                    pct = (data.close - data.pre_close) / data.pre_close * 100
                    change_pcts.append(pct)
            
            if len(change_pcts) < 5:
                continue
            
            # 检查是否满足涨幅条件
            # 条件2: 前3日涨幅
            cum_3days = sum(change_pcts[:3]) if len(change_pcts) >= 3 else 0
            threshold_3days = 15 if is_main_board else 20
            
            # 条件3: 前5日涨幅
            cum_5days = sum(change_pcts[:5]) if len(change_pcts) >= 5 else 0
            threshold_5days = 20 if is_main_board else 25
            
            # 条件5: 前15日涨幅
            cum_15days = sum(change_pcts[:15]) if len(change_pcts) >= 15 else 0
            
            # 条件6: 前20日涨幅
            cum_20days = sum(change_pcts[:20]) if len(change_pcts) >= 20 else 0
            
            # 如果涨幅满足任一条件，输出详细信息
            if (cum_3days > threshold_3days or 
                cum_5days > threshold_5days or 
                cum_15days > 50 or 
                cum_20days > 50):
                
                print(f"\n日期: {date_str}")
                print(f"  前3日涨幅: {cum_3days:.2f}% (阈值:{threshold_3days}%) {'✓ 满足' if cum_3days > threshold_3days else '✗'}")
                print(f"  前5日涨幅: {cum_5days:.2f}% (阈值:{threshold_5days}%) {'✓ 满足' if cum_5days > threshold_5days else '✗'}")
                print(f"  前15日涨幅: {cum_15days:.2f}% (阈值:50%) {'✓ 满足' if cum_15days > 50 else '✗'}")
                print(f"  前20日涨幅: {cum_20days:.2f}% (阈值:50%) {'✓ 满足' if cum_20days > 50 else '✗'}")
                print(f"  成交量类型: {current_chance.volume_type}")
                print(f"  空头组合: {current_chance.bearish_pattern if current_chance.bearish_pattern else '无'}")
                print(f"  当日K线: O={current_data.open:.2f}, C={current_data.close:.2f}, H={current_data.high:.2f}, L={current_data.low:.2f}")
                
                # 执行完整的R点检测
                plugin_result = r_service._check_deviation(stock_code, test_date)
                if plugin_result.triggered:
                    print(f"  ✓✓✓ 触发乖离率偏离: {plugin_result.reason}")
                else:
                    print(f"  ✗✗✗ 未触发乖离率偏离（涨幅满足但其他条件不满足）")
        
        print("\n" + "="*100)
        print("测试完成")
        print("="*100)
        
        r_service.clear_cache()
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python test_deviation_debug.py <股票代码> <开始日期> <结束日期>")
        print("示例: python test_deviation_debug.py SZ300564 2025-01-01 2025-11-30")
        sys.exit(1)
    
    stock_code = sys.argv[1]
    start_date = sys.argv[2]
    end_date = sys.argv[3]
    
    test_deviation_plugin(stock_code, start_date, end_date)

