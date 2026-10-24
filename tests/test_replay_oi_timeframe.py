"""Regression: the replay must honour the `timeframe` argument of
fetch_open_interest_history, as production does.

Production OIEngine.fetch_oi asks for fetch_open_interest_history(symbol,
timeframe="1h", limit=2) and compares the live OI with history[-2] (an hourly
bar). The replay ignored `timeframe` and returned the last two 5-minute rows, so
the OI change covered only ~5 minutes and the label was NEUTRAL for 100% of the
1,102 signals in Run #81 (OI data was present, the comparison window was wrong).
"""
import unittest

import pandas as pd

from engines.oi_engine import OIEngine
from tools.historical_replay import HistoricalStore, ReplayExchange

SYM = "ETH/USDT:USDT"
START = pd.Timestamp("2026-10-01T00:00:00Z")


def exchange_with_oi(end, hourly_growth=0.01, hours=6):
    ts = pd.date_range(START, END_TS := START + pd.Timedelta(hours=hours), freq="5min", tz=None)
    ts = pd.DatetimeIndex(ts).tz_localize("UTC") if ts.tz is None else ts
    # continuous growth: +1% per hour => ~0.083% per 5 minutes
    vals = [1000.0 * (1 + hourly_growth) ** ((t - START).total_seconds() / 3600) for t in ts]
    oi = {SYM: pd.DataFrame({"timestamp": ts, "sumOpenInterestValue": vals})}
    return ReplayExchange(HistoricalStore(candles={}, funding={}, oi=oi, end=end))


class OiTimeframeTests(unittest.TestCase):
    END = pd.Timestamp("2026-10-01T03:00:00Z")

    def test_hourly_history_returns_hourly_spaced_rows(self):
        ex = exchange_with_oi(self.END)
        hist = ex.fetch_open_interest_history(SYM, timeframe="1h", limit=2)
        self.assertEqual(len(hist), 2)
        gap_min = (hist[-1]["timestamp"] - hist[-2]["timestamp"]) / 60000
        self.assertEqual(gap_min, 60)
        self.assertEqual(hist[-1]["timestamp"], int(self.END.timestamp() * 1000))   # never beyond the cutoff

    def test_one_hour_oi_move_is_visible_to_the_engine(self):
        ex = exchange_with_oi(self.END, hourly_growth=0.01)
        oi = OIEngine().fetch_oi(ex, SYM)
        self.assertTrue(oi.get("data_available"), oi)
        res = OIEngine().analyze(oi["current_oi"], oi["previous_oi"], price_change=0.5, direction="LONG")
        self.assertGreater(res["oi_change_pct"], 0.5)          # ~1% over an hour
        self.assertEqual(res["oi_signal"], "CONFIRMED")

    def test_five_minute_request_is_unchanged(self):
        ex = exchange_with_oi(self.END)
        hist = ex.fetch_open_interest_history(SYM, timeframe="5m", limit=2)
        self.assertEqual((hist[-1]["timestamp"] - hist[-2]["timestamp"]) / 60000, 5)

    def test_no_fabrication_when_hourly_grid_has_gaps(self):
        ex = exchange_with_oi(self.END)
        df = ex.store.oi[SYM]
        ex.store.oi[SYM] = df[df["timestamp"].dt.minute != 0]   # drop every on-the-hour snapshot
        self.assertEqual(ex.fetch_open_interest_history(SYM, timeframe="1h", limit=2), [])


if __name__ == "__main__":
    unittest.main()
