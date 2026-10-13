"""Research-only replay cadence (BACKTEST_STEP_MINUTES, default 60 = unchanged).

Why: production scans every 5 minutes at arbitrary offsets, so the forming 1H
candle usually carries a partial move. At exact hour boundaries it is open-only
(close == open), so inputs derived from it (e.g. the OI engine's price_chg) are
exactly 0. Sub-hourly cutoffs let the replay see partial forming candles, built
only from 5m candles that had closed by the cutoff.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from test_historical_replay_boundary import build_store, SYM  # noqa: E402
from test_historical_replay_sink_regression import synthetic_store  # noqa: E402

import tools.historical_replay as hr  # noqa: E402
from engines.oi_engine import OIEngine  # noqa: E402
from config import CONFIG  # noqa: E402

FIVE = pd.Timedelta(minutes=5)


def scramble(store, T):
    """Copy of the store where everything NOT knowable at T is replaced by garbage."""
    twin = hr.HistoricalStore(candles={}, funding={}, oi={}, end=T)
    for (sym, tf), df in store.candles.items():
        d = df.copy()
        unfinished = d["timestamp"] + hr.INTERVAL_DELTAS[tf] > T      # not fully closed at T
        future = d["timestamp"] > T                                   # not even opened at T
        d.loc[unfinished, ["high", "low", "close", "volume"]] = 9999.0
        d.loc[future, "open"] = 7777.0
        twin.candles[(sym, tf)] = d
    return twin


class CutoffTests(unittest.TestCase):
    START = pd.Timestamp("2026-10-01T00:00:00Z")
    END = pd.Timestamp("2026-10-01T03:00:00Z")

    def test_default_step_is_hourly_and_matches_legacy_timeline(self):
        legacy = [self.START + pd.Timedelta(hours=h) for h in range(0, 4)]
        self.assertEqual(hr.replay_cutoffs(self.START, self.END, 60), legacy)

    def test_sub_hourly_steps(self):
        c = hr.replay_cutoffs(self.START, self.END, 15)
        self.assertEqual(len(c), 3 * 4 + 1)
        self.assertEqual(c[0], self.START)
        self.assertEqual(c[-1], self.END)
        self.assertTrue(all((b - a) == pd.Timedelta(minutes=15) for a, b in zip(c, c[1:])))

    def test_unaligned_start_is_rounded_up_never_before_start(self):
        c = hr.replay_cutoffs(pd.Timestamp("2026-10-01T00:07:00Z"), self.END, 15)
        self.assertEqual(c[0], pd.Timestamp("2026-10-01T00:15:00Z"))

    def test_invalid_steps_rejected(self):
        for bad in (0, 3, 7, 25, 90, -5):
            with self.assertRaises(ValueError, msg=str(bad)):
                hr.validate_step_minutes(bad)
        for ok in (5, 10, 15, 20, 30, 60):
            self.assertEqual(hr.validate_step_minutes(ok), ok)

    def test_env_default_and_override(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BACKTEST_STEP_MINUTES", None)
            self.assertEqual(hr.step_minutes_from_env(), 60)
        with mock.patch.dict(os.environ, {"BACKTEST_STEP_MINUTES": "15"}):
            self.assertEqual(hr.step_minutes_from_env(), 15)


class CausalityAtSubHourlyCutoffsTests(unittest.TestCase):
    def test_frames_depend_only_on_information_available_at_each_minute_cutoff(self):
        base = pd.Timestamp("2026-10-01T12:00:00Z")
        for minutes in range(5, 60, 5):
            T = base + pd.Timedelta(minutes=minutes)
            real = build_store(base, sentinel=False)
            real.end = T
            twin = scramble(real, T)
            lr, lt = hr.ReplayMarketLoader(real), hr.ReplayMarketLoader(twin)
            for tf in hr.INTERVAL_DELTAS:
                pd.testing.assert_frame_equal(lr._frame(SYM, tf, None), lt._frame(SYM, tf, None), obj=f"{tf}@{T}")
            hr.assert_replay_boundary(real)

    def test_mid_hour_forming_1h_candle_is_built_only_from_closed_5m_candles(self):
        base = pd.Timestamp("2026-10-01T12:00:00Z")
        store = build_store(base, sentinel=True)          # future values 150/50/140/999 at >= 12:00
        store.end = base - pd.Timedelta(minutes=30)                  # 11:30: sentinels are in the future
        row = hr.ReplayMarketLoader(store)._frame(SYM, "1h", None).iloc[-1]
        self.assertEqual(row["timestamp"], pd.Timestamp("2026-10-01T11:00:00Z"))
        m5 = store.candles[(SYM, "5m")]
        seg = m5[(m5.timestamp >= row["timestamp"]) & (m5.timestamp + FIVE <= store.end)]
        self.assertEqual(len(seg), 6)
        self.assertEqual((row["high"], row["low"], row["close"]), (seg.high.max(), seg.low.min(), seg.iloc[-1].close))
        self.assertAlmostEqual(row["volume"], seg.volume.sum())

    def test_ticker_is_last_completed_5m_close_mid_hour_and_legacy_on_the_hour(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        store = build_store(end, sentinel=False)
        ex = hr.ReplayExchange(store)
        m5 = store.candles[(SYM, "5m")]
        h1 = store.candles[(SYM, "1h")]
        store.end = end + pd.Timedelta(minutes=20)
        last5 = m5[m5.timestamp + FIVE <= store.end].iloc[-1]
        self.assertEqual(ex.fetch_ticker(SYM)["last"], float(last5["close"]))
        store.end = end
        last1h = h1[h1.timestamp + pd.Timedelta(hours=1) <= end].iloc[-1]
        self.assertEqual(ex.fetch_ticker(SYM)["last"], float(last1h["close"]))      # unchanged hourly behaviour


class StructuralOiUnlockTests(unittest.TestCase):
    def test_price_change_is_zero_on_the_hour_but_not_mid_hour(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        store = build_store(end, sentinel=False)
        loader = hr.ReplayMarketLoader(store)
        store.end = end
        on_hour = float(loader._frame(SYM, "1h", None)["close"].pct_change().iloc[-1] * 100)
        self.assertEqual(on_hour, 0.0)
        moved = []
        for m in range(5, 60, 5):
            store.end = end + pd.Timedelta(minutes=m)
            moved.append(float(loader._frame(SYM, "1h", None)["close"].pct_change().iloc[-1] * 100))
        self.assertTrue(any(abs(v) > 0 for v in moved))
        big = max(moved, key=abs)
        label = OIEngine().analyze(1020.0, 1000.0, big if abs(big) > 0.1 else 0.3, "LONG")["oi_signal"]
        self.assertIn(label, {"CONFIRMED", "WEAK", "DIVERGING"})   # no longer structurally NEUTRAL


class EndToEndTests(unittest.TestCase):
    END = "2026-10-01T12:00:00Z"

    def _run(self, env, days=3 / 24, cooldown=None):
        store = synthetic_store(pd.Timestamp(self.END))
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "storage"))
            out = Path(tmp) / "r.json"
            os.chdir(tmp)
            try:
                with mock.patch.object(hr, "DAYS", days), mock.patch.object(hr, "load_store", lambda s, e: store), \
                     mock.patch.object(hr, "RESULTS", out), mock.patch.dict(os.environ, dict({"BACKTEST_END": self.END}, **env)), \
                     mock.patch.dict(CONFIG, {} if cooldown is None else {"signal_cooldown_hours": cooldown}):
                    hr.run()
            finally:
                os.chdir(cwd)
            return json.loads(out.read_text())

    def test_hourly_default_unchanged_and_sub_hourly_runs_more_scans(self):
        legacy = self._run({})
        explicit = self._run({"BACKTEST_STEP_MINUTES": "60"})
        self.assertEqual(legacy["results"], explicit["results"])               # explicit 60 == default, row for row
        self.assertEqual(legacy["metadata"]["step_minutes"], 60)
        half = self._run({"BACKTEST_STEP_MINUTES": "30"}, cooldown=0)   # no cooldown: isolate the cadence effect
        self.assertEqual(half["metadata"]["step_minutes"], 30)
        minutes = {pd.Timestamp(r["replay_time"]).minute for r in half["results"]}
        self.assertTrue(minutes - {0}, f"no signals at :30 cutoffs: {minutes}")
        # same symbol+direction is scored differently mid-hour (partial forming candle): cadence matters
        by_key = {}
        for r in half["results"]:
            by_key.setdefault((r["symbol"], r["direction"]), {})[pd.Timestamp(r["replay_time"]).minute] = r["score"]
        self.assertTrue(any(len(v) == 2 and v[0] != v[30] for v in by_key.values()))


if __name__ == "__main__":
    unittest.main()
