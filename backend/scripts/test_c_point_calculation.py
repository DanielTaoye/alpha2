"""
测试C点实时计算
"""
import sys
import os
from datetime import datetime, timedelta

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl as DailyDataRepositoryImpl
from application.services.cr_point_service import CRPointService
from domain.models.kline import KLineData
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

def test_stock(stock_code: str):
    """测试单只股票的C点计算"""
    print("=" * 80)
    print(f"Testing C-point calculation for: {stock_code}")
    print("=" * 80)
    
    try:
        # 初始化服务
        cr_service = CRPointService()
        daily_data_repo = DailyDataRepositoryImpl()
        
        # 获取日线数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=600)
        
        print(f"\nFetching daily data from {start_date.date()} to {end_date.date()}...")
        daily_data_list = daily_data_repo.find_by_date_range(
            stock_code, 
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        if not daily_data_list:
            print(f"[ERROR] No daily data found for {stock_code}")
            return False
        
        print(f"Found {len(daily_data_list)} daily records")
        
        # 转换为KLineData格式
        kline_data = []
        for data in daily_data_list:
            kline = KLineData(
                time=data.date,
                open=data.open,
                high=data.high,
                low=data.low,
                close=data.close,
                volume=data.volume
            )
            kline_data.append(kline)
        
        print(f"\nAnalyzing C-points...")
        
        # 分析并保存C点
        result = cr_service.analyze_and_save_cr_points(
            stock_code=stock_code,
            stock_name='',
            kline_data=kline_data
        )
        
        c_points_count = result['c_points_count']
        print(f"\n[SUCCESS] Found {c_points_count} C-points for {stock_code}")
        
        if c_points_count > 0:
            print("\nC-points details:")
            for cp in result['c_points'][:5]:  # 显示前5个
                print(f"  - Date: {cp['triggerDate']}, Score: {cp['score']:.2f}, Strategy: {cp['strategyName']}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        logger.error(f"测试失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # 测试之前诊断中发现有C点的股票
    test_stocks = ['SH600066', 'SH600075']
    
    for stock_code in test_stocks:
        success = test_stock(stock_code)
        print("\n")
        if not success:
            print(f"[FAILED] {stock_code}")

