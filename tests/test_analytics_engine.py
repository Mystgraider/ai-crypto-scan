import unittest
from unittest.mock import patch

from reports.analytics_engine import AnalyticsEngine


class AnalyticsEngineTests(unittest.TestCase):
    def test_uses_recorded_realized_r_not_fixed_tp_assumptions(self):
        signals = [
            {
                "status": "TP3_HIT", "direction": "LONG",
                "entry": "100", "initial_sl": "98", "exit_price": "106",
                "realized_r": "3.0", "grade": "A",
            },
            {
                "status": "SL_HIT", "direction": "LONG",
                "entry": "100", "initial_sl": "98", "exit_price": "98",
                "realized_r": "-1.0", "grade": "A",
            },
            {
                "status": "OPEN_TP1", "direction": "LONG",
                "entry": "100", "initial_sl": "98", "sl": "100",
                "realized_r": "", "grade": "B",
            },
        ]
        with patch("reports.analytics_engine.load_signals", return_value=signals):
            result = AnalyticsEngine().compute()

        self.assertEqual(result["total_signals"], 3)
        self.assertEqual(result["open"], 1)
        self.assertEqual(result["resolved"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["losses"], 1)
        self.assertEqual(result["net_r"], 2.0)
        self.assertEqual(result["expectancy_r"], 1.0)
        self.assertEqual(result["profit_factor"], 3.0)

    def test_unresolved_terminal_trade_is_excluded_from_performance_metrics(self):
        signals = [
            {
                "status": "TP3_HIT", "direction": "LONG",
                "grade": "A", "realized_r": "",
            },
            {
                "status": "SL_HIT", "direction": "LONG",
                "entry": "100", "initial_sl": "98", "exit_price": "98",
                "realized_r": "-1.0", "grade": "A",
            },
            {
                "status": "EXPIRED", "direction": "LONG", "grade": "B",
            },
        ]
        with patch("reports.analytics_engine.load_signals", return_value=signals):
            result = AnalyticsEngine().compute()

        self.assertEqual(result["closed"], 3)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["unresolved"], 1)
        self.assertEqual(result["wins"], 0)
        self.assertEqual(result["losses"], 1)
        self.assertEqual(result["win_rate"], 0.0)
        self.assertEqual(result["net_r"], -1.0)
        self.assertEqual(result["expectancy_r"], -1.0)
        self.assertEqual(result["grade_stats"]["A"]["resolved"], 1)
        self.assertEqual(result["grade_stats"]["A"]["wins"], 0)
        self.assertEqual(result["grade_stats"]["A"]["net_r"], -1.0)

    def test_legacy_terminal_signal_can_derive_r_from_prices(self):
        signal = {
            "status": "TP3_HIT", "direction": "SHORT",
            "entry": "100", "initial_sl": "102", "exit_price": "94",
            "realized_r": "", "grade": "A",
        }
        self.assertEqual(AnalyticsEngine._terminal_r(signal), 3.0)


if __name__ == "__main__":
    unittest.main()
