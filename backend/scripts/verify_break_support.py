
import sys
import unittest
from datetime import datetime, date
from unittest.mock import MagicMock, patch

# Add path to find modules
sys.path.append("c:\\Users\\lenovo\\Desktop\\alpha_strategy_v2\\backend")

from domain.services.r_point_plugin_service import RPointPluginService

class TestDynamicBreakSupport(unittest.TestCase):
    def setUp(self):
        # Patch dependencies to avoid DB connection in __init__
        with patch("infrastructure.persistence.daily_repository_impl.DailyRepositoryImpl"), \
             patch("infrastructure.persistence.daily_chance_repository_impl.DailyChanceRepositoryImpl"), \
             patch("domain.services.config_service.get_config_service"):
            self.service = RPointPluginService()
        
        # Mock caches
        self.service._daily_cache = {}
        self.service._daily_chance_cache = {}
        # Mock finding dates to avoid DB queries
        self.service._get_previous_trading_dates_from_cache = MagicMock()

    def test_dynamic_support_logic(self):
        stock_code = "000001"
        check_date_str = "2024-01-02"
        prev_date_str = "2024-01-01"
        c_date_str = "2023-12-31" # Some previous C date

        # Setup Mock Data
        # 1. Current data (Check Date)
        mock_current_data = MagicMock()
        mock_current_data.close = 10.5 # Closing price
        self.service._daily_cache[check_date_str] = mock_current_data

        # 2. Previous Trading Date Setup
        self.service._get_previous_trading_dates_from_cache.return_value = [prev_date_str]

        # 3. Previous Day Support Ticket (11.00)
        mock_prev_chance = MagicMock()
        mock_prev_chance.support_price = 1100 # 11.00 * 100
        self.service._daily_chance_cache[prev_date_str] = mock_prev_chance

        # 4. C Day Support Ticket (12.00)
        mock_c_chance = MagicMock()
        mock_c_chance.support_price = 1200 # 12.00 * 100
        self.service._daily_chance_cache[c_date_str] = mock_c_chance

        # Case 1: Close (10.5) < Prev (11.0) and C (12.0). 
        # Max Support = 12.0. Result: Break.
        c_point_date = datetime.strptime(c_date_str, "%Y-%m-%d")
        is_break, final_support, _, detail = self.service._is_break_dynamic_support(
            stock_code, check_date_str, c_point_date
        )
        self.assertTrue(is_break)
        self.assertEqual(final_support, 12.0)
        self.assertIn("C日", detail)

        # Case 2: C Support is Lower (10.0), Prev Support (11.0).
        # Max Support = 11.0. Close (10.5). Result: Break.
        mock_c_chance.support_price = 1000 # 10.00
        is_break, final_support, _, detail = self.service._is_break_dynamic_support(
            stock_code, check_date_str, c_point_date
        )
        self.assertTrue(is_break)
        self.assertEqual(final_support, 11.0)
        self.assertIn("前日", detail)

        # Case 3: Close (11.5) > Prev (11.0) and C (10.0)
        # Max = 11.0. Result: No Break.
        mock_current_data.close = 11.5
        is_break, final_support, _, _ = self.service._is_break_dynamic_support(
            stock_code, check_date_str, c_point_date
        )
        self.assertFalse(is_break)

        # Case 4: No C Date (None)
        # Should rely on Prev (11.0). Close (11.5) -> No Break.
        is_break, final_support, _, _ = self.service._is_break_dynamic_support(
            stock_code, check_date_str, None
        )
        self.assertFalse(is_break)
        self.assertEqual(final_support, 11.0)

        # Case 5: No C Date (None), Close (10.5) < Prev (11.0) -> Break
        mock_current_data.close = 10.5
        is_break, final_support, _, _ = self.service._is_break_dynamic_support(
            stock_code, check_date_str, None
        )
        self.assertTrue(is_break)
        self.assertEqual(final_support, 11.0)

if __name__ == '__main__':
    unittest.main()
