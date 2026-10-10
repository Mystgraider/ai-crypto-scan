"""Regression: fetch_oi() must parse Binance Vision daily `metrics` files whatever
form create_time takes. The original parser only accepted epoch numbers, so a
datetime/date string timestamp dropped every row and OI was UNAVAILABLE for 100%
of replay signals (Run #68)."""
import unittest

import pandas as pd

import tools.historical_replay as hr

START = pd.Timestamp("2026-09-10T00:00:00Z")
END = pd.Timestamp("2026-09-10T23:59:00Z")
SM, EM = int(START.timestamp() * 1000), int(END.timestamp() * 1000)


def _frame(stamps):
    return pd.DataFrame({
        "create_time": stamps, "symbol": "ETHUSDT",
        "sum_open_interest": [1.0, 1.1, 1.2],
        "sum_open_interest_value": [1000.0, 1100.0, 1200.0],
    })


class OiParserTests(unittest.TestCase):
    def _run_all(self, stamps):
        orig = hr._download_archive_csv
        hr._download_archive_csv = lambda url: _frame(stamps).copy()
        try:
            return hr.fetch_oi("ETHUSDT", SM, EM)  # window inside a single day => one file
        finally:
            hr._download_archive_csv = orig

    def test_datetime_strings(self):
        out = self._run_all(["2026-09-10 00:05:00", "2026-09-10 00:10:00", "2026-09-10 00:15:00"])
        self.assertEqual(len(out), 3)

    def test_date_only_strings(self):
        out = self._run_all(["2026-09-10", "2026-09-10", "2026-09-10"])
        self.assertGreaterEqual(len(out), 1)

    def test_values_and_timezone_utc(self):
        out = self._run_all(["2026-09-10 00:05:00", "2026-09-10 00:10:00", "2026-09-10 00:15:00"])
        self.assertEqual(list(out["sumOpenInterestValue"]), [1000.0, 1100.0, 1200.0])
        self.assertEqual(out["timestamp"].iloc[0], pd.Timestamp("2026-09-10T00:05:00Z"))

    def test_epoch_milliseconds_still_work(self):
        ms = [int(pd.Timestamp(f"2026-09-10T00:{m:02d}:00Z").timestamp() * 1000) for m in (5, 10, 15)]
        out = self._run_all(ms)
        self.assertEqual(len(out), 3)
        self.assertEqual(out["timestamp"].iloc[0], pd.Timestamp("2026-09-10T00:05:00Z"))

    def test_rows_outside_window_dropped(self):
        out = self._run_all(["2026-09-10 00:05:00", "2026-09-12 00:10:00", "2026-09-10 00:15:00"])
        self.assertNotIn(pd.Timestamp("2026-09-12T00:10:00Z"), list(out["timestamp"]))

    def test_unparseable_timestamps_yield_empty_not_crash(self):
        out = self._run_all(["garbage", "", "not-a-time"])
        self.assertEqual(len(out), 0)


if __name__ == "__main__":
    unittest.main()
