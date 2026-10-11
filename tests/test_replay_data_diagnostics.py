"""Coverage and emitted-feature diagnostics tests for historical replay."""

import unittest

import pandas as pd

from tools.historical_replay import (
    HistoricalStore,
    feature_telemetry_diagnostics,
    market_data_diagnostics,
)


class ReplayDataDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2026-10-01T00:00:00Z")
        self.end = pd.Timestamp("2026-10-08T00:00:00Z")

    def test_market_data_diagnostics_count_only_rows_inside_replay_window(self):
        store = HistoricalStore(
            candles={},
            funding={
                "ETH/USDT:USDT": pd.DataFrame({
                    "timestamp": pd.to_datetime([
                        "2026-09-30T23:00:00Z",
                        "2026-10-02T00:00:00Z",
                        "2026-10-08T00:00:00Z",
                        "2026-10-08T01:00:00Z",
                    ], utc=True),
                    "fundingRate": [0.001, 0.002, 0.003, 0.004],
                })
            },
            oi={
                "ETH/USDT:USDT": pd.DataFrame({
                    "timestamp": pd.to_datetime([
                        "2026-10-01T00:00:00Z",
                        "2026-10-04T12:00:00Z",
                    ], utc=True),
                    "sumOpenInterestValue": [100.0, 110.0],
                })
            },
            end=self.end,
        )
        result = market_data_diagnostics(store, self.start, self.end)
        eth = result["ETH/USDT:USDT"]
        self.assertEqual(eth["funding"]["rows_in_window"], 2)
        self.assertEqual(eth["funding"]["first_timestamp_in_window"], "2026-10-02T00:00:00+00:00")
        self.assertEqual(eth["funding"]["last_timestamp_in_window"], "2026-10-08T00:00:00+00:00")
        self.assertEqual(eth["open_interest"]["rows_in_window"], 2)
        self.assertTrue(eth["open_interest"]["has_data_in_window"])

    def test_missing_sources_are_explicitly_reported_as_no_coverage(self):
        store = HistoricalStore(candles={}, funding={}, oi={}, end=self.end)
        result = market_data_diagnostics(store, self.start, self.end)
        self.assertFalse(result["ETH/USDT:USDT"]["funding"]["has_data_in_window"])
        self.assertFalse(result["ETH/USDT:USDT"]["open_interest"]["has_data_in_window"])
        self.assertEqual(result["ETH/USDT:USDT"]["funding"]["rows_in_window"], 0)

    def test_feature_telemetry_separates_neutral_oi_and_funding_zero(self):
        result = feature_telemetry_diagnostics([
            {"oi_signal": "NEUTRAL", "funding_pct_raw": 0.0},
            {"oi_signal": "UNAVAILABLE", "funding_pct_raw": None},
            {"oi_signal": None, "funding_pct_raw": 0.001},
        ])
        self.assertEqual(result["oi_signal_counts"], {
            "NEUTRAL": 1, "UNAVAILABLE": 1, "MISSING": 1
        })
        self.assertEqual(result["funding_pct_raw"], {
            "missing_or_non_numeric": 1, "zero": 1, "nonzero": 1
        })
        self.assertIn("do not prove", result["interpretation_limit"])


if __name__ == "__main__":
    unittest.main()
