"""Regression: PR #110 telemetry sink must survive candidates that are ranked
but rejected afterwards (live validation / entry drift). Before the fix the sink
was never cleared between replay cycles, so a stale snapshot was popped for a
later signal with the same (symbol, direction) and the score guard aborted the
whole replay with replay_telemetry_score_mismatch."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import tools.historical_replay as hr

FIVE = hr.INTERVAL_DELTAS["5m"]
NINE = ("trend_score", "quality_score", "rs_score", "funding_pct_raw", "stoch_k",
        "macd_hist", "bb_pct_b", "mtf_4h", "mtf_15m")


def _agg(m5, tf):
    g = m5.set_index("timestamp").resample(hr.INTERVAL_DELTAS[tf], origin="epoch", label="left", closed="left")
    return g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()


def synthetic_store(end, seed=11):
    rng = np.random.default_rng(seed)
    ts = pd.date_range(end - pd.Timedelta(hours=520), end + pd.Timedelta(hours=80), freq=FIVE, tz="UTC", inclusive="left")
    candles, funding = {}, {}
    for k, sym in enumerate(hr.DATA_SYMBOLS):
        n = len(ts)
        r = rng.normal(0, 0.0035, n) + 0.0004 * np.sin(np.arange(n) / (180 + 40 * k))
        c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) * (1 + rng.uniform(0, .002, n)); l = np.minimum(o, c) * (1 - rng.uniform(0, .002, n))
        m5 = pd.DataFrame(dict(timestamp=ts, open=o, high=h, low=l, close=c, volume=rng.uniform(50, 500, n)))
        candles[(sym, "5m")] = m5
        for tf in ("15m", "1h", "4h"):
            candles[(sym, tf)] = _agg(m5, tf)
        funding[sym] = pd.DataFrame({"timestamp": [ts[0]], "fundingRate": [0.0001 * (k + 1)]})
    return hr.HistoricalStore(candles=candles, funding=funding, oi={}, end=end)


class SinkSurvivesPostRankRejectionTests(unittest.TestCase):
    def test_replay_completes_and_attributes_telemetry_after_post_rank_rejections(self):
        end = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1)
        store = synthetic_store(end)
        first = end - pd.Timedelta(hours=18)
        orig = hr.ReplayExchange.fetch_ticker

        def drifting(self, symbol):
            t = dict(orig(self, symbol))
            if self.store.end <= first + pd.Timedelta(hours=2):
                t["last"] *= 1.05
            return t

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "storage"), exist_ok=True)
            out = Path(tmp) / "result.json"
            os.chdir(tmp)
            try:
                with mock.patch.object(hr, "DAYS", 18 / 24),                      mock.patch.object(hr, "load_store", lambda s, e: store),                      mock.patch.object(hr, "RESULTS", out),                      mock.patch.object(hr.ReplayExchange, "fetch_ticker", drifting):
                    hr.run()
            finally:
                os.chdir(cwd)
            rows = json.loads(out.read_text())["results"]
        self.assertGreater(len(rows), 0)
        for r in rows:
            for f in NINE:
                self.assertIsNotNone(r[f], f"{f} @ {r['replay_time']} {r['symbol']} {r['direction']}")


if __name__ == "__main__":
    unittest.main()
