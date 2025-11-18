"""
测试新增的3个C点插件
插件6: R后回支撑位发C
插件7: 阳包阴发C
插件8: 横盘修整后突破发C
"""
import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl as DailyDataRepositoryImpl
from application.services.cr_point_service import CRPointService
from domain.models.kline import KLineData
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def test_stock(stock_code: str, days: int = 180):
    """测试单只股票的新C点插件"""
    print("=" * 80)
    print(f"测试新C点插件: {stock_code}")
    print("=" * 80)
    
    try:
        # 初始化服务
        cr_service = CRPointService()
        daily_data_repo = DailyDataRepositoryImpl()
        
        # 获取日线数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print(f"\n获取日线数据: {start_date.date()} 至 {end_date.date()}...")
        daily_data_list = daily_data_repo.find_by_date_range(
            stock_code, 
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        if not daily_data_list:
            print(f"[错误] 未找到股票 {stock_code} 的日线数据")
            return False
        
        print(f"找到 {len(daily_data_list)} 条日线数据")
        
        # 转换为KLineData格式
        kline_data = []
        for data in daily_data_list:
            kline = KLineData(
                time=data.date,
                open=data.open,
                high=data.high,
                low=data.low,
                close=data.close,
                volume=data.volume,
                liangbi=getattr(data, 'liangbi', 0.0),
                weibi=getattr(data, 'weibi', 0.0)
            )
            kline_data.append(kline)
        
        print(f"\n分析CR点...")
        
        # 实时分析C点和R点
        result = cr_service.analyze_cr_points(
            stock_code=stock_code,
            stock_name="测试股票",
            kline_data=kline_data
        )
        
        print(f"\n分析结果:")
        print(f"  C点总数: {result.get('c_point_count', 0)}")
        print(f"  R点总数: {result.get('r_point_count', 0)}")
        
        # 查找使用新插件的C点
        c_points = result.get('c_points', [])
        new_plugin_c_points = []
        
        for c in c_points:
            plugins = c.get('plugins', [])
            for plugin in plugins:
                plugin_name = plugin.get('pluginName', '')
                if plugin_name in ['R后回支撑位', '阳包阴', '横盘修整后突破']:
                    new_plugin_c_points.append({
                        'date': c.get('triggerDate'),
                        'plugin': plugin_name,
                        'reason': plugin.get('reason')
                    })
        
        if new_plugin_c_points:
            print(f"\n触发新插件的C点 ({len(new_plugin_c_points)}个):")
            print("-" * 80)
            for item in new_plugin_c_points:
                print(f"  日期: {item['date']}")
                print(f"  插件: {item['plugin']}")
                print(f"  原因: {item['reason']}")
                print("-" * 80)
        else:
            print("\n未触发新插件")
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n[错误] 测试失败: {e}")
        return False


if __name__ == "__main__":
    # 测试多只股票
    test_stocks = [
        "SH600000",  # 浦发银行
        "SZ000001",  # 平安银行
        "SH601318",  # 中国平安
    ]
    
    if len(sys.argv) > 1:
        # 如果提供了股票代码参数，只测试该股票
        test_stocks = [sys.argv[1]]
    
    success_count = 0
    for stock_code in test_stocks:
        if test_stock(stock_code):
            success_count += 1
        print("\n")
    
    print("=" * 80)
    print(f"测试完成: {success_count}/{len(test_stocks)} 只股票测试成功")
    print("=" * 80)

