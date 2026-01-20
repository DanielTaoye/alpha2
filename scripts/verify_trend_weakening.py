
import sys
import os
from datetime import datetime, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from domain.services.r_point_plugin_service import RPointPluginService, RPointPluginResult
from domain.models.daily_chance import DailyChance

class MockKLine:
    def __init__(self, close, open_val, prev_close):
        self.close = close
        self.open = open_val
        self.prev_close = prev_close

def test_trend_weakening():
    service = RPointPluginService()
    
    # Mock data
    stock_code = "TEST001"
    date = datetime(2024, 1, 1)
    date_str = date.strftime('%Y-%m-%d')
    
    # Common mock data
    ma_data = {'ma20': [10.5]} # MA20 > Close (10.0) usually
    macd_data = {'dif': [-0.1], 'dea': [0.1]} # Dead cross: DIF < DEA
    current_index = 0
    
    # Case 1: All conditions met (Trend Weakening)
    # - Stock Nature: 波段
    # - Volume: A
    # - MACD: Dead Cross
    # - MA20: Close (10.0) <= MA20 (10.5)
    # - Risk: Big Drop (3%+, Body 3%+)
    print("\n--- Test Case 1: Standard Trigger (Big Drop) ---")
    
    daily_chance = DailyChance(stock_nature="波段", volume_type="A")
    service._daily_chance_cache = {date_str: daily_chance}
    
    kline_data = [MockKLine(close=10.0, open_val=10.4, prev_close=10.5)] 
    # Drop: (10.5 - 10.0) / 10.5 = 4.76% > 3%
    # Body: (10.4 - 10.0) / 10.5 = 3.8% > 3%
    
    result = service._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_data)
    print(f"Triggered: {result.triggered}, Reason: {result.reason}")
    assert result.triggered == True
    assert "大阴线" in result.reason

    # Case 2: Short term stock (Should not trigger)
    print("\n--- Test Case 2: Short Term Stock (Fail) ---")
    daily_chance = DailyChance(stock_nature="短线", volume_type="A")
    service._daily_chance_cache = {date_str: daily_chance}
    result = service._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_data)
    print(f"Triggered: {result.triggered}")
    assert result.triggered == False

    # Case 3: No Volume Increase (Should not trigger)
    print("\n--- Test Case 3: No valid volume (Fail) ---")
    daily_chance = DailyChance(stock_nature="波段", volume_type="X") # Invalid volume
    service._daily_chance_cache = {date_str: daily_chance}
    result = service._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_data)
    print(f"Triggered: {result.triggered}")
    assert result.triggered == False

    # Case 4: MACD Gold Cross (Should not trigger)
    print("\n--- Test Case 4: MACD Gold Cross (Fail) ---")
    daily_chance = DailyChance(stock_nature="波段", volume_type="A")
    service._daily_chance_cache = {date_str: daily_chance}
    gold_macd = {'dif': [0.2], 'dea': [0.1]} # DIF > DEA
    result = service._check_trend_weakening(stock_code, date, ma_data, gold_macd, current_index, kline_data)
    print(f"Triggered: {result.triggered}")
    assert result.triggered == False

    # Case 5: Close > MA20 (Should not trigger)
    print("\n--- Test Case 5: Close > MA20 (Fail) ---")
    daily_chance = DailyChance(stock_nature="波段", volume_type="A")
    service._daily_chance_cache = {date_str: daily_chance}
    ma20_low = {'ma20': [9.0]} # Close 10.0 > 9.0
    result = service._check_trend_weakening(stock_code, date, ma20_low, macd_data, current_index, kline_data)
    print(f"Triggered: {result.triggered}")
    assert result.triggered == False

    # Case 6: Bearish Pattern (Trigger)
    print("\n--- Test Case 6: Bearish Pattern (Trigger) ---")
    daily_chance = DailyChance(stock_nature="波段", volume_type="A", bearish_pattern="乌云盖顶")
    service._daily_chance_cache = {date_str: daily_chance}
    kline_normal = [MockKLine(close=10.0, open_val=10.1, prev_close=10.2)] # Small drop, but pattern exists
    result = service._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_normal)
    print(f"Triggered: {result.triggered}, Reason: {result.reason}")
    assert result.triggered == True
    assert "空头组合" in result.reason

    # Case 7: Divergence Pattern in Bearish Pattern field (Trigger)
    print("\n--- Test Case 7: Divergence Pattern (Trigger) ---")
    daily_chance = DailyChance(stock_nature="波段", volume_type="A", bearish_pattern="冲高回落阳线")
    service._daily_chance_cache = {date_str: daily_chance}
    result = service._check_trend_weakening(stock_code, date, ma_data, macd_data, current_index, kline_normal)
    print(f"Triggered: {result.triggered}, Reason: {result.reason}")
    assert result.triggered == True
    assert "空头组合" in result.reason # Or divergence, depends on which check hits first, here pattern check is first

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_trend_weakening()
