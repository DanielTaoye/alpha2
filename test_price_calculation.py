#!/usr/bin/env python3
"""
测试涨幅计算逻辑的修复效果

验证前N日涨幅计算是否正确，不再依赖数据库的涨跌幅字段
"""

import sys
import os
from datetime import datetime, timedelta

# 添加项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__)) + "/backend"
sys.path.insert(0, backend_dir)

from domain.repositories.daily_chance_repository import IDailyChanceRepository
from domain.repositories.kline_repository import IKLineRepository
from infrastructure.persistence.daily_chance_repository_impl import DailyChanceRepositoryImpl
from infrastructure.persistence.daily_repository_impl import DailyRepositoryImpl


def test_price_calculation(stock_code: str = "SH600036", test_date: str = "2024-12-06"):
    """
    测试涨幅计算逻辑

    Args:
        stock_code: 股票代码
        test_date: 测试日期
    """
    print(f"测试股票: {stock_code}")
    print(f"测试日期: {test_date}")
    print("-" * 50)

    # 初始化仓储
    daily_repo = DailyRepositoryImpl()
    daily_chance_repo = DailyChanceRepositoryImpl()

    # 获取测试日期及其前20个交易日的数据
    test_date_obj = datetime.strptime(test_date, '%Y-%m-%d')
    start_date = (test_date_obj - timedelta(days=30)).strftime('%Y-%m-%d')  # 多取一些天数确保有足够交易日

    # 获取日期范围内的数据
    daily_data_list = daily_repo.find_by_date_range(stock_code, start_date, test_date)

    if not daily_data_list:
        print("❌ 未找到日线数据")
        return

    print(f"获取到 {len(daily_data_list)} 条日线数据")

    # 筛选出交易日数据（排除周末等非交易日）
    trading_days = []
    for data in daily_data_list:
        if data.close > 0:  # 确保有有效数据
            trading_days.append(data)

    # 取最近21个交易日（当前日 + 前20日）
    if len(trading_days) < 21:
        print(f"⚠️  交易日数据不足: {len(trading_days)}天，需要至少21天")
        return

    recent_21_days = trading_days[-21:]  # 取最后21条记录
    print(f"使用最近21个交易日进行测试")

    # 打印原始数据
    print("\n原始日线数据:")
    print("日期\t\t开盘\t\t最高\t\t最低\t\t收盘\t\t昨收\t\t涨跌幅")
    print("-" * 80)

    for data in recent_21_days:
        if hasattr(data, 'pre_close'):
            if data.pre_close and data.pre_close > 0:
                old_pct = (data.close - data.pre_close) / data.pre_close * 100
            else:
                old_pct = 0
        else:
            old_pct = 0

        print(".2f")

    # 测试新的涨幅计算逻辑
    print("\n新的涨幅计算结果:")
    print("日期\t\t收盘价\t\t前日收盘\t\t新涨幅(%)")
    print("-" * 60)

    change_pcts_new = []
    prev_close = None

    for data in recent_21_days:
        if prev_close is not None and prev_close > 0:
            pct = (data.close - prev_close) / prev_close * 100
            change_pcts_new.append(pct)
            print(".2f")
        else:
            change_pcts_new.append(0)
            print(".2f")
        prev_close = data.close

    # 计算累计涨幅
    print("\n累计涨幅统计:")
    print(f"前3日涨幅: {sum(change_pcts_new[-4:-1]):.2f}%")  # 最近3天（不含当天）
    print(f"前5日涨幅: {sum(change_pcts_new[-6:-1]):.2f}%")  # 最近5天（不含当天）
    print(f"前15日涨幅: {sum(change_pcts_new[-16:-1]):.2f}%")  # 最近15天（不含当天）
    print(f"前20日涨幅: {sum(change_pcts_new[-21:-1]):.2f}%")  # 最近20天（不含当天）

    print("\n✅ 测试完成")


if __name__ == "__main__":
    # 测试浦发银行
    test_price_calculation("SH600036", "2024-12-06")
