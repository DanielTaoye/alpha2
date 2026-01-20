
import sys
import os
from datetime import datetime, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from domain.services.r_point_plugin_service import RPointPluginService, RPointPluginResult
from domain.models.daily_chance import DailyChance
from domain.services.kline_pattern_service import KLinePatternService

class MockDaily:
    def __init__(self, close, open_val, date, prev_close=None):
        self.close = close
        self.open = open_val
        self.high = max(close, open_val)
        self.low = min(close, open_val)
        self.date = date
        self.prev_close = prev_close

def test_deviation_scenario8():
    service = RPointPluginService()
    
    stock_code = "SH600000" # Main board
    today = datetime(2024, 1, 20)
    today_str = today.strftime('%Y-%m-%d')
    days = []
    
    # Generate previous 6 days dates
    for i in range(1, 10):
        d = today - timedelta(days=i)
        days.append(d)
    
    # Mock is_main_board
    KLinePatternService.is_main_board = lambda x: True
    
    print("\n--- Case 1: Trigger via Rally > 20% + G-Vol + Big Drop ---")
    
    # Mock Data Construction
    # Base (T-6): 10.0
    # T-1: 12.5 (Rise 25% > 20%)
    # Today (T): 11.5 (Drop 1.0 from 12.5 -> 8%, Body also > 5%)
    
    # T-6 (Base)
    t6_data = MockDaily(10.0, 10.0, days[5])
    # T-5 to T-2 (Arbitrary climb)
    t5_data = MockDaily(10.5, 10.0, days[4])
    t4_data = MockDaily(11.0, 10.5, days[3])
    t3_data = MockDaily(11.5, 11.0, days[2])
    t2_data = MockDaily(12.0, 11.5, days[1])
    # T-1 (Peak)
    t1_data = MockDaily(12.5, 12.0, days[0])
    
    # Today Data (Big Drop G-Vol)
    # Prev Close 12.5. Today Open 12.5, Close 11.5.
    # Drop: (12.5 - 11.5)/12.5 = 8%
    # Body: (12.5 - 11.5)/12.5 = 8%
    curr_data = MockDaily(11.5, 12.5, today) 
    
    # Mock Cache
    service._daily_cache = {
        today_str: curr_data,
        days[0].strftime('%Y-%m-%d'): t1_data,
        days[1].strftime('%Y-%m-%d'): t2_data,
        days[2].strftime('%Y-%m-%d'): t3_data,
        days[3].strftime('%Y-%m-%d'): t4_data,
        days[4].strftime('%Y-%m-%d'): t5_data,
        days[5].strftime('%Y-%m-%d'): t6_data,
    }
    
    # Mock Daily Chance (Short Term + G Vol)
    dc = DailyChance(stock_nature="短线", volume_type="G")
    service._daily_chance_cache = {today_str: dc}
    
    # Mock Repo find_by_date for previous dates lookup if check_deviation uses it internally 
    # (actually check_deviation uses _get_previous_trading_dates_from_cache which relies on DB or cache keys)
    # We must ensure keys in `_daily_cache` are sufficient if we populated it?
    # Actually `_check_deviation` fetches prev data via:
    # prev_dates = self._get_previous_trading_dates_from_cache(date_str, stock_code)
    # prev_data_list = [self._daily_cache.get(d) ...]
    # So we need to mock `_get_previous_trading_dates_from_cache`
    def mock_get_prev(d_str, s_code):
        return [d.strftime('%Y-%m-%d') for d in days[:7]] # Return T-1 to T-7
    service._get_previous_trading_dates_from_cache = mock_get_prev
    
    # Execute
    res = service._check_deviation(stock_code, today, {}, 0) # ma_data empty is fine for this check?
    # Wait, check_deviation does `deviation` calculation first. If ma_data is None it skips it? Yes.
    # But does it skip logic? No.
    # But it checks `deviation` value later? 
    # "if deviation is not None and deviation > threshold" -> This is Condition 7.
    # Condition 8 is independent? Yes.
    
    print(f"Triggered: {res.triggered}, Reason: {res.reason}")
    assert res.triggered == True
    assert "条件8" in res.reason
    assert "G型放量+大阴线" in res.reason

    print("\n--- Case 2: Trigger via 5-Consecutive Yang + 2-Day Drop ---")
    # T-5 to T-1 all Yang.
    # Rise > 20%.
    # Trigger 2: 2-Day Drop > 6%.
    
    # T-6 Base: 10.0
    # T-5: Open 10.0, Close 10.4 (Yang)
    t5_data = MockDaily(10.4, 10.0, days[4])
    # T-4: Open 10.4, Close 10.8 (Yang)
    t4_data = MockDaily(10.8, 10.4, days[3])
    # T-3: Open 10.8, Close 11.2 (Yang)
    t3_data = MockDaily(11.2, 10.8, days[2])
    # T-2: Open 11.2, Close 11.6 (Yang)
    t2_data = MockDaily(11.6, 11.2, days[1])
    # T-1: Open 11.6, Close 12.0 (Yang) -> Gain (12-10)/10 = 20%. 
    # Wait, 20% exactly. Threshold is > 20%. Let's bump T-1 to 12.1.
    t1_data = MockDaily(12.1, 11.6, days[0]) # Green? No, Open 11.6 Close 12.1 -> Yang.
    # Gain (12.1 - 10.0) / 10.0 = 21% > 20%.
    
    # Trigger 2: 
    # Today (T): Yin. Yesterday (T-1) Yin? 
    # Wait, user requirement: "连续2日阴线（含今日）" -> Today and Yesterday must be Yin.
    # But in the setup above T-1 was Yang to satisfy "5 consecutive Yang" for the Rally condition.
    # User says: "前5日（不含今日）≥5连阳... OR (Today is 2-day Yin ...)"
    # Ah, the Rally condition "Prefix" must be satisfied by T-1...T-5.
    # Then the "Trigger Condition" checks Today(T) and Yesterday(T-1).
    # If T-1 needs to be Yin for Trigger 2, it conflicts with T-1 being Yang for Rally Condition B (5-consecutive Yang).
    # UNLESS:
    # Rally Option A: Just Rise > 20% (Doesn't require consecutive Yang).
    # Rally Option B: 5-consecutive Yang (T-1 to T-5).
    # If we use Option B, T-1 MUST be Yang.
    # If Trigger 2 requires T-1 be Yin ("连续2日阴线"), then Option B + Trigger 2 is IMPOSSIBLE.
    # Thus, Trigger 2 can only work with Rally Option A (Just Rise > 20% without requiring T-1 be Yang).
    # Or, does "前5日" mean T-2 to T-6? No, usually T-1 to T-5.
    # Let's assumes Option A for Trigger 2 test.
    
    # Redefine T-1 for Trigger 2:
    # T-1: Open 12.5, Close 12.1 (Yin). Rise (12.1 - 10.0)/10 = 21% > 20%. (Valid for Option A)
    t1_data = MockDaily(12.1, 12.5, days[0])
    
    # T-2 (Base for Drop calc): Must be valid for Drop check.
    # Trigger 2: (T-2 Close - T Close) / T-2 Close > 6%.
    # T-2 Close is 11.6.  Target Drop > 6%.
    # 11.6 * (1-0.06) = 10.9.
    # Today Close should be < 10.9. Say 10.8.
    curr_data = MockDaily(10.8, 11.0, today) # Yin: Open 11.0 Close 10.8.
    
    # Update cache
    service._daily_cache[days[0].strftime('%Y-%m-%d')] = t1_data
    service._daily_cache[days[1].strftime('%Y-%m-%d')] = t2_data # T-2 11.6
    service._daily_cache[today_str] = curr_data
    
    dc_case2 = DailyChance(stock_nature="波段", volume_type="A") # Not G-vol
    service._daily_chance_cache = {today_str: dc_case2}
    
    res = service._check_deviation(stock_code, today, {}, 0)
    print(f"Triggered: {res.triggered}, Reason: {res.reason}")
    assert res.triggered == True
    assert "2连阴" in res.reason

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_deviation_scenario8()
