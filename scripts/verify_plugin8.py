
import sys
import os
from datetime import datetime, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from domain.services.r_point_plugin_service import RPointPluginService, RPointPluginResult
from domain.models.daily_chance import DailyChance

class MockKLine:
    def __init__(self, close, open_val, prev_close, time=None):
        self.close = close
        self.open = open_val
        self.prev_close = prev_close
        self.time = time
        self.ma60 = 20.0 # High value to ensure Low C check passes (Close < MA60)

class MockDaily:
    def __init__(self, close, time):
        self.close = close
        self.date = time

def test_plugin8_refinement():
    service = RPointPluginService()
    
    # Mock data
    stock_code = "TEST008"
    today = datetime(2024, 1, 10)
    today_str = today.strftime('%Y-%m-%d')
    days_ago_1 = datetime(2024, 1, 9)
    days_ago_1_str = days_ago_1.strftime('%Y-%m-%d')
    days_ago_2 = datetime(2024, 1, 8)
    days_ago_2_str = days_ago_2.strftime('%Y-%m-%d')
    days_ago_10 = datetime(2024, 1, 1) # Old C
    days_ago_10_str = days_ago_10.strftime('%Y-%m-%d')
    
    # Mock cache for previous dates lookup
    service._daily_cache = {
        # Mock daily closes
        today_str: MockDaily(10.0, today),
        days_ago_1_str: MockDaily(10.2, days_ago_1),
        days_ago_2_str: MockDaily(10.5, days_ago_2),
        days_ago_10_str: MockDaily(12.0, days_ago_10) # Low C
    }
    
    # Mock helper method for prev dates
    def mock_get_prev_dates(date_str, stock_code_arg):
        return [days_ago_1_str, days_ago_2_str]
    service._get_previous_trading_dates_from_cache = mock_get_prev_dates
    
    # Mock _is_break_dynamic_support for fallback logic check
    def mock_is_break_dynamic_support(stock_code, check_date_str, c_date):
        # Always return False to prove we didn't use fallback when we shouldn't
        return False, 0, 0, ""
    service._is_break_dynamic_support = mock_is_break_dynamic_support

    # Common parameters
    ma_data = {'ma60': [20.0, 20.0, 20.0]} 
    # Need to mock MACD Dead Cross to pass Condition 3
    macd_data = {'dif': [-0.5, -0.4], 'dea': [-0.4, -0.3]} 
    # Current Index (assume 0 is today, list is reversed? No, list usually chron. 
    # But current_index in plugin service usually points to 'today' in the list.
    # Let's assume list is [days_ago..., today].
    # But wait, the plugin uses current_index to access lists.
    # Let's verify usage.
    # plugin uses current_index to access ma_data lists.
    # So if ma_data lists have length 1, current_index should be 0.
    
    current_index = 0
    kline_data = [MockKLine(10.0, 10.0, 10.1, time=today)] # Today
    
    # --- Case 1: C point is RECENT (Yesterday) ---
    print("\n--- Case 1: Recent C (Yesterday) ---")
    c_date_recent = days_ago_1 # Yesterday
    c_date_recent_str = days_ago_1_str
    
    # Setup C point support
    # C Support = 10.1 (Above Today Close 10.0) -> Should Trigger
    daily_chance_c = DailyChance(support_price=1010.0) # 10.10
    service._daily_chance_cache[c_date_recent_str] = daily_chance_c
    
    # Also need Low C check to pass: Low C Close < Low C MA60
    # C Close 10.2 < MA60 20.0 (from mock) -> Pass
    
    # We need to ensure logic finds Low C index. 
    # The code scans backwards from current_index looking for c_point_date.
    # If our kline_data only has today, it won't find yesterday's kline.
    # So we must provide kline_data including history for the scan loop.
    kline_list_case1 = [
        MockKLine(10.2, 10.2, 10.3, time=days_ago_1), # Index 0
        MockKLine(10.0, 10.0, 10.1, time=today)       # Index 1
    ]
    ma_data_case1 = {'ma60': [20.0, 20.0]}
    macd_data_case1 = {'dif': [-0.4, -0.5], 'dea': [-0.3, -0.4]} # index 0, index 1
    # Check index 1 (Today)
    
    # Run check
    # Expect: Trigger because Today(10.0) < C_Support(10.1)
    result = service._check_downtrend_break_support(stock_code, today, ma_data_case1, macd_data_case1, 1, kline_list_case1, c_date_recent)
    print(f"Triggered: {result.triggered}, Reason: {result.reason}")
    assert result.triggered == True
    assert "近3日有C" in result.reason

    # --- Case 2: Recent C but NOT broken ---
    print("\n--- Case 2: Recent C (Not Broken) ---")
    # C Support = 9.0 (Below Today Close 10.0) -> No Trigger
    daily_chance_c_low = DailyChance(support_price=900.0) # 9.00
    service._daily_chance_cache[c_date_recent_str] = daily_chance_c_low
    
    result = service._check_downtrend_break_support(stock_code, today, ma_data_case1, macd_data_case1, 1, kline_list_case1, c_date_recent)
    print(f"Triggered: {result.triggered}")
    assert result.triggered == False

    # --- Case 3: Old C (Fallback to loop) ---
    print("\n--- Case 3: Old C (Fallback) ---")
    c_date_old = days_ago_10 
    # Scan loop needs to find it. 
    # We can't easily mock full history in list, but we can hack the 'scan' or 'Low C' check?
    # Actually, if Scan fails, it returns False.
    # Let's mock kline for Old C.
    kline_list_old = [MockKLine(12.0, 12.0, 12.1, time=days_ago_10)] + [MockKLine(10.0,10.0,10.0)]*8 + [MockKLine(10.0, 10.0, 10.1, time=today)]
    # Index 0 is old c, Index 9 is today? 
    # len is 1+8+1 = 10. Index 9.
    
    # We need to reset `_is_break_dynamic_support` to return True to prove fallback was called
    service._is_break_dynamic_support = lambda s, d, c: (True, 10.5, 10.0, "Fallback Trigger")
    
    ma_data_old = {'ma60': [20.0]*10}
    macd_data_old = {'dif': [-0.5]*10, 'dea': [-0.4]*10}
    
    # Also need Old C data in cache/repo for 'Low C Close < MA60' check if needed (it checks kline first)
    # Our MockKLine(12.0) checks vs 20.0 -> OK.
    
    result = service._check_downtrend_break_support(stock_code, today, ma_data_old, macd_data_old, 9, kline_list_old, c_date_old)
    print(f"Triggered: {result.triggered}, Reason: {result.reason}")
    assert result.triggered == True
    assert "Fallback Trigger" in result.reason # Must come from the fallback loop
    assert "近3日有C" not in result.reason

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_plugin8_refinement()
