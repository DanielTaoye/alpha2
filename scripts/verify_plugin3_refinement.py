
import sys
import os
from datetime import datetime, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from domain.services.r_point_plugin_service import RPointPluginService, RPointPluginResult
from domain.models.daily_chance import DailyChance

class MockDaily:
    def __init__(self, close, open_val, date):
        self.close = close
        self.open = open_val
        self.date = date

def test_plugin3_refinement():
    service = RPointPluginService()
    
    stock_code = "SH600000"
    today = datetime(2024, 1, 20)
    today_str = today.strftime('%Y-%m-%d')
    days_ago_1 = datetime(2024, 1, 19)
    days_ago_1_str = days_ago_1.strftime('%Y-%m-%d')
    days_ago_2 = datetime(2024, 1, 18)
    
    # Mock Prev Dates lookup
    service._get_previous_trading_dates_from_cache = lambda d, s: [days_ago_1_str, days_ago_2.strftime('%Y-%m-%d')]

    # Common Setup:
    # Prev Day: Open 10.0, Close 10.0 (Doji). Mid = 10.0.
    # Today: Open 9.9, Close 9.8. (Unreversed, Close < Mid)
    t1_data = MockDaily(10.0, 10.0, days_ago_1)
    curr_data = MockDaily(9.8, 9.9, today)
    
    service._daily_cache = {
        days_ago_1_str: t1_data,
        today_str: curr_data
    }
    
    # Prev Chance: "StrongToWeak"
    prev_chance = DailyChance(bearish_pattern="强转弱")
    service._daily_chance_cache[days_ago_1_str] = prev_chance
    
    # --- Case 1: Short Term (Legacy Logic) ---
    print("\n--- Case 1: Short Term (Legacy Logic) ---")
    # Today Chance: Stock Nature "Short", Volume "G"
    curr_chance_short = DailyChance(stock_nature="短线", volume_type="G")
    service._daily_chance_cache[today_str] = curr_chance_short
    
    # Empty MA/MACD (should ignore for Short term)
    res = service._check_strong_to_weak_not_reversed(stock_code, today, {}, {}, 0)
    print(f"Triggered: {res.triggered}, Reason: {res.reason}")
    assert res.triggered == True
    assert "G型放量" in res.reason

    # --- Case 2: Medium-Long Term (Missing Conditions) ---
    print("\n--- Case 2: Medium-Long Term (Missing Conds) ---")
    curr_chance_ml = DailyChance(stock_nature="中长线", volume_type="G")
    service._daily_chance_cache[today_str] = curr_chance_ml
    
    # MA20: 8.0 (Close 9.8 > MA20 -> No Break)
    ma_data_safe = {'ma20': [8.0]}
    # MACD: DIF > DEA (Gold Cross)
    macd_data_safe = {'dif': [0.5], 'dea': [0.4]}
    
    res = service._check_strong_to_weak_not_reversed(stock_code, today, ma_data_safe, macd_data_safe, 0)
    print(f"Triggered: {res.triggered}")
    assert res.triggered == False # Expect False because MA20 not broken and No Dead Cross

    # --- Case 3: Medium-Long Term (Triggered) ---
    print("\n--- Case 3: Medium-Long Term (Triggered) ---")
    # Cond 1: Break MA20 (Close 9.8). MA20 = 10.0.
    ma_data_trigger = {'ma20': [10.0] * 5} # Close 9.8 < 10.0 -> Break
    
    # Cond 2: Dead Cross in last 5 days.
    # Today index 4. List length 5.
    # Day 0: DIF < DEA. Day 4: DIF > DEA.
    # Current Index = 4 (Today).
    macd_data_trigger = {
        'dif': [0.4, 0.5, 0.6, 0.7, 0.8], 
        'dea': [0.5, 0.4, 0.3, 0.2, 0.1]
    } 
    # Index 0 (T-4): DIF 0.4 < DEA 0.5 -> Dead Cross existed.
    
    res = service._check_strong_to_weak_not_reversed(stock_code, today, ma_data_trigger, macd_data_trigger, 4)
    print(f"Triggered: {res.triggered}, Reason: {res.reason}")
    assert res.triggered == True
    assert "中长线限制" in res.reason

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_plugin3_refinement()
