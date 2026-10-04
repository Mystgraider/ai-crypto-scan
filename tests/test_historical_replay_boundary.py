import unittest

import pandas as pd

from tools.historical_replay import (
    HistoricalStore,
    INTERVAL_DELTAS,
    ReplayMarketLoader,
    assert_replay_boundary,
)


class ReplayCandleBoundaryTests(unittest.TestCase):
    def test_visible_view_preserves_forming_candle_at_cutoff(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        candles = {}
        for timeframe, delta in INTERVAL_DELTAS.items():
            ts = [end - 2 * delta, end - delta, end, end + delta]
            candles[("TEST/USDT:USDT", timeframe)] = pd.DataFrame(
                {
                    "timestamp": ts,
                    "open": [1.0, 1.0, 1.0, 1.0],
                    "high": [1.0, 1.0, 1.0, 1.0],
                    "low": [1.0, 1.0, 1.0, 1.0],
                    "close": [1.0, 1.0, 1.0, 1.0],
                    "volume": [1.0, 1.0, 1.0, 1.0],
                }
            )

        store = HistoricalStore(candles=candles, funding={}, oi={}, end=end)
        assert_replay_boundary(store)
        loader = ReplayMarketLoader(store)

        for timeframe in INTERVAL_DELTAS:
            frame = loader._frame("TEST/USDT:USDT", timeframe, None)
            self.assertEqual(frame.iloc[-1]["timestamp"], end)
            self.assertEqual(
                frame.iloc[-2]["timestamp"],
                end - INTERVAL_DELTAS[timeframe],
            )
            self.assertEqual(len(frame), 3)

    def test_future_candle_is_not_visible(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        delta = INTERVAL_DELTAS["15m"]
        candles = {
            ("TEST/USDT:USDT", "15m"): pd.DataFrame(
                {
                    "timestamp": [end - delta, end, end + delta],
                    "open": [1.0, 1.0, 1.0],
                    "high": [1.0, 1.0, 1.0],
                    "low": [1.0, 1.0, 1.0],
                    "close": [1.0, 1.0, 1.0],
                    "volume": [1.0, 1.0, 1.0],
                }
            )
        }
        store = HistoricalStore(candles=candles, funding={}, oi={}, end=end)
        frame = ReplayMarketLoader(store)._frame(
            "TEST/USDT:USDT", "15m", None
        )
        self.assertFalse((frame["timestamp"] > end).any())


if __name__ == "__main__":
    unittest.main()
