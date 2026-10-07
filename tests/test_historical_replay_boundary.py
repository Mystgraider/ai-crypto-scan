"""Adversarial historical-replay causality and production-window tests."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from tools.historical_replay import (
    HistoricalStore,
    INTERVAL_DELTAS,
    ReplayMarketLoader,
    assert_replay_boundary,
)
from config import CONFIG


SYM = "TEST/USDT:USDT"
FIVE = INTERVAL_DELTAS["5m"]
FUT_HIGH, FUT_LOW, FUT_CLOSE, FUT_VOL = 150.0, 50.0, 140.0, 999.0


def _aggregate(m5: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    delta = INTERVAL_DELTAS[timeframe]
    g = m5.set_index("timestamp").resample(
        delta, origin="epoch", label="left", closed="left"
    )
    out = g.agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    )
    return out.dropna().reset_index()


def build_store(end: pd.Timestamp, back_h=520, fwd_h=12, sentinel=True):
    rng = np.random.default_rng(7)
    ts = pd.date_range(
        end - pd.Timedelta(hours=back_h),
        end + pd.Timedelta(hours=fwd_h),
        freq=FIVE,
        tz="UTC",
        inclusive="left",
    )
    n = len(ts)
    close = 100 + np.cumsum(rng.normal(0, 0.03, n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.01, 0.08, n)
    low = np.minimum(open_, close) - rng.uniform(0.01, 0.08, n)
    volume = rng.uniform(1, 10, n)
    m5 = pd.DataFrame(
        {"timestamp": ts, "open": open_, "high": high, "low": low,
         "close": close, "volume": volume}
    )

    if sentinel:
        fut = m5["timestamp"] >= end
        m5.loc[fut, "open"] = 100.0
        m5.loc[fut, "high"] = FUT_HIGH
        m5.loc[fut, "low"] = FUT_LOW
        m5.loc[fut, "close"] = FUT_CLOSE
        m5.loc[fut, "volume"] = FUT_VOL
        prior = m5.loc[m5["timestamp"] == end - FIVE, "close"].iloc[0]
        m5.loc[m5["timestamp"] == end, "open"] = prior

    candles = {(SYM, "5m"): m5}
    for tf in ("15m", "1h", "4h"):
        candles[(SYM, tf)] = _aggregate(m5, tf)
    return HistoricalStore(candles=candles, funding={}, oi={}, end=end)


class CausalBoundaryTests(unittest.TestCase):
    CUTOFFS = [
        pd.Timestamp("2026-10-01T12:00:00Z"),
        pd.Timestamp("2026-10-01T13:00:00Z"),
        pd.Timestamp("2026-10-01T15:00:00Z"),
        pd.Timestamp("2026-10-01T16:00:00Z"),
    ]

    def test_future_ohlcv_never_leaks(self):
        for end in self.CUTOFFS:
            store = build_store(end)
            loader = ReplayMarketLoader(store)
            assert_replay_boundary(store)
            for tf in INTERVAL_DELTAS:
                frame = loader._frame(SYM, tf, None)
                self.assertFalse((frame["timestamp"] > end).any(), f"{tf}@{end}")
                self.assertLess(frame["high"].max(), FUT_HIGH, f"{tf}@{end}")
                self.assertGreater(frame["low"].min(), FUT_LOW, f"{tf}@{end}")
                self.assertNotEqual(frame["close"].iloc[-1], FUT_CLOSE, f"{tf}@{end}")
                self.assertLess(frame["volume"].max(), FUT_VOL, f"{tf}@{end}")

    def test_exact_cutoff_forming_row_is_open_only(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        store = build_store(end)
        loader = ReplayMarketLoader(store)
        for tf, delta in INTERVAL_DELTAS.items():
            frame = loader._frame(SYM, tf, None)
            last, prev = frame.iloc[-1], frame.iloc[-2]
            self.assertEqual(last["timestamp"], end, tf)
            self.assertTrue(
                last["open"] == last["high"] == last["low"] == last["close"], tf
            )
            self.assertEqual(last["volume"], 0.0, tf)
            self.assertEqual(prev["timestamp"], end - delta, tf)

    def test_mid_4h_forming_row_uses_only_closed_5m(self):
        for end in (
            pd.Timestamp("2026-10-01T13:00:00Z"),
            pd.Timestamp("2026-10-01T15:00:00Z"),
        ):
            store = build_store(end)
            frame = ReplayMarketLoader(store)._frame(SYM, "4h", None)
            start = end.floor(INTERVAL_DELTAS["4h"])
            row = frame.iloc[-1]
            m5 = store.candles[(SYM, "5m")]
            seg = m5[
                (m5["timestamp"] >= start)
                & (m5["timestamp"] + FIVE <= end)
            ]
            archived = store.candles[(SYM, "4h")]
            archived = archived[archived["timestamp"] == start].iloc[0]

            self.assertEqual(row["timestamp"], start)
            self.assertEqual(row["open"], archived["open"])
            self.assertEqual(row["high"], seg["high"].max())
            self.assertEqual(row["low"], seg["low"].min())
            self.assertEqual(row["close"], seg.iloc[-1]["close"])
            self.assertAlmostEqual(row["volume"], seg["volume"].sum())
            self.assertNotEqual(row["high"], FUT_HIGH)
            self.assertNotEqual(row["close"], FUT_CLOSE)
            self.assertLess(row["volume"], archived["volume"])

    def test_last_completed_candle_is_not_shifted(self):
        end = pd.Timestamp("2026-10-01T13:00:00Z")
        store = build_store(end)
        loader = ReplayMarketLoader(store)
        for tf, delta in INTERVAL_DELTAS.items():
            frame = loader._frame(SYM, tf, None)
            self.assertEqual(frame.iloc[-1]["timestamp"], end.floor(delta))
            self.assertEqual(
                frame.iloc[-2]["timestamp"], end.floor(delta) - delta
            )
            self.assertLessEqual(
                frame.iloc[-2]["timestamp"] + delta, end
            )

    def test_production_window_limits_are_respected(self):
        end = pd.Timestamp("2026-10-01T13:00:00Z")
        store = build_store(end)
        loader = ReplayMarketLoader(store)
        for tf in INTERVAL_DELTAS:
            frame = loader._frame(SYM, tf, None)
            self.assertLessEqual(len(frame), CONFIG["ohlcv_limit"], tf)
        self.assertLessEqual(
            len(loader._frame(SYM, "4h", None)), CONFIG["ohlcv_4h_limit"]
        )
        self.assertEqual(
            len(loader._frame(SYM, "1h", 5)), 5
        )
        self.assertEqual(
            len(loader._frame(SYM, "4h", 5)), 5
        )

    def test_boundary_assertion_rejects_old_leaky_predicate(self):
        end = pd.Timestamp("2026-10-01T13:00:00Z")
        store = build_store(end)

        def leaky(self, symbol, timeframe, limit):
            df = self.store.candles[(symbol, timeframe)]
            df = df[df["timestamp"] <= self.store.end]
            return df.tail(limit).reset_index(drop=True) if limit else df.reset_index(drop=True)

        with mock.patch.object(ReplayMarketLoader, "_frame", leaky):
            with self.assertRaises(AssertionError):
                assert_replay_boundary(store)


class InformationAvailabilityTests(unittest.TestCase):
    def test_scrambling_unavailable_values_cannot_change_frames(self):
        base_end = pd.Timestamp("2026-10-01T12:00:00Z")
        for hours in range(9):
            end = base_end + pd.Timedelta(hours=hours)
            real = build_store(end, sentinel=False)
            twin = build_store(end, sentinel=False)

            for (sym, tf), df in twin.candles.items():
                d = df.copy()
                delta = INTERVAL_DELTAS[tf]
                unfinished = d["timestamp"] + delta > end
                future = d["timestamp"] > end
                n = int(unfinished.sum())
                if n:
                    d.loc[unfinished, ["high", "low", "close", "volume"]] = 9999.0
                if int(future.sum()):
                    d.loc[future, "open"] = 7777.0
                twin.candles[(sym, tf)] = d

            lr = ReplayMarketLoader(real)
            lt = ReplayMarketLoader(twin)
            for tf in INTERVAL_DELTAS:
                pd.testing.assert_frame_equal(
                    lr._frame(SYM, tf, None),
                    lt._frame(SYM, tf, None),
                    obj=f"{tf}@{end}",
                )


class WarmupTests(unittest.TestCase):
    def test_warmup_matches_100_candle_4h_production_window_plus_margin(self):
        from tools.historical_replay import WARMUP_HOURS
        expected = CONFIG["ohlcv_4h_limit"] * 4 + 48
        self.assertEqual(WARMUP_HOURS, expected)
        self.assertGreaterEqual(WARMUP_HOURS, 448)


if __name__ == "__main__":
    unittest.main()
