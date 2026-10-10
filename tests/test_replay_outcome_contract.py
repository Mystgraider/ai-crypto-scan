"""Outcome-tracker contract for the historical replay.

Locks the documented behavior of tools.historical_replay.historical_outcome and
proves it agrees with the production state machine (tracker.signal_tracker
.SignalTracker._check) candle-by-candle, and that LONG/SHORT are exact mirrors.
"""
import unittest

import numpy as np
import pandas as pd

from tools.historical_replay import historical_outcome
from tracker.signal_tracker import SignalTracker

T0 = pd.Timestamp("2026-10-01T12:00:00Z")
FIVE = pd.Timedelta(minutes=5)


def candles(rows, first_offset=1):
    """rows: [(high, low)] one per 5m candle, the first opening first_offset*5m after T0."""
    ts = pd.to_datetime([T0 + FIVE * (first_offset + i) for i in range(len(rows))], utc=True)
    return pd.DataFrame({
        "timestamp": ts,
        "open": [(h + l) / 2 for h, l in rows], "high": [h for h, _ in rows],
        "low": [l for _, l in rows], "close": [(h + l) / 2 for h, l in rows], "volume": 1.0,
    })


def sig(direction, entry=100.0, sl=98.0, tp1=103.0, tp2=106.0, tp3=110.0):
    if direction == "SHORT":
        sl, tp1, tp2, tp3 = 2 * entry - sl, 2 * entry - tp1, 2 * entry - tp2, 2 * entry - tp3
    return {"direction": direction, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "_replay_time": T0.isoformat()}


class DocumentedBehaviourTests(unittest.TestCase):
    def test_sl_first_when_one_candle_spans_stop_and_target(self):
        for d in ("LONG", "SHORT"):
            s = sig(d)
            hi, lo = (111.0, 97.0) if d == "LONG" else (103.0, 89.0)
            out = historical_outcome(s, candles([(hi, lo)]))
            self.assertEqual(out["status"], "SL_HIT", d)

    def test_one_candle_crossing_tp1_and_tp2_records_both_and_arms_breakeven(self):
        for d in ("LONG", "SHORT"):
            s = sig(d)
            up = d == "LONG"
            c1 = (107.0, 99.0) if up else (101.0, 93.0)          # crosses TP1 and TP2, not TP3
            c2 = (100.5, 99.9) if up else (100.1, 99.5)          # then returns to entry
            out = historical_outcome(s, candles([c1, (104.0, 100.5) if up else (99.5, 96.0), c2]))
            self.assertEqual(out["status"], "BREAKEVEN_AFTER_TP2", d)
            self.assertEqual(out["milestones"], ["TP1", "TP2"], d)

    def test_one_candle_crossing_all_targets_is_tp3_with_ordered_milestones(self):
        for d in ("LONG", "SHORT"):
            s = sig(d)
            out = historical_outcome(s, candles([(111.0, 99.0)] if d == "LONG" else [(101.0, 89.0)]))
            self.assertEqual(out["status"], "TP3_HIT", d)
            self.assertEqual(out["milestones"], ["TP1", "TP2"], d)

    def test_breakeven_after_tp1_not_counted_as_full_loss(self):
        for d in ("LONG", "SHORT"):
            s = sig(d); up = d == "LONG"
            out = historical_outcome(s, candles([(104.0, 100.5) if up else (99.5, 96.0),
                                                 (100.4, 99.9) if up else (100.1, 99.6)]))
            self.assertEqual(out["status"], "BREAKEVEN_AFTER_TP1", d)

    def test_full_stop_without_milestones_is_sl_hit(self):
        for d in ("LONG", "SHORT"):
            s = sig(d)
            out = historical_outcome(s, candles([(100.5, 97.5)] if d == "LONG" else [(102.5, 99.5)]))
            self.assertEqual(out["status"], "SL_HIT", d)
            self.assertEqual(out["milestones"], [], d)

    def test_expiry_boundary_and_unresolved_labels(self):
        s = sig("LONG")
        quiet = [(100.5, 99.5)] * 3
        self.assertEqual(historical_outcome(s, candles(quiet))["status"], "EXPIRED")  # window non-empty, no event
        self.assertEqual(historical_outcome(s, candles([], 1))["status"], "OPEN")      # no future data at all
        # a candle that would complete AFTER the 72h expiry must be ignored
        late = candles([(111.0, 99.0)], first_offset=72 * 12)   # opens exactly at expiry
        self.assertEqual(historical_outcome(s, late)["status"], "OPEN")

    def test_policy_candle_opening_at_signal_time_is_excluded(self):
        """DOCUMENTED POLICY (metadata: 'future candles begin strictly after replay
        timestamp'). Under review: in Run #68 ~1% of resolved trades resolved in the
        first included candle, so an equal share may be hidden here (mostly LONG stops)."""
        s = sig("LONG")
        self.assertEqual(historical_outcome(s, candles([(100.5, 90.0)], first_offset=0))["status"], "OPEN")


class DifferentialAgainstProductionTrackerTests(unittest.TestCase):
    @staticmethod
    def classify(prod_terminal, prior_status):
        if prod_terminal == "SL_HIT":
            return {"OPEN_TP2": "BREAKEVEN_AFTER_TP2", "OPEN_TP1": "BREAKEVEN_AFTER_TP1"}.get(prior_status, "SL_HIT")
        return prod_terminal

    def _walk(self, s, df):
        tracker = SignalTracker.__new__(SignalTracker)
        status, sl, prior = "OPEN", s["sl"], "OPEN"
        for _, c in df.iterrows():
            res = tracker._check(s["direction"], float(c["close"]), s["entry"], sl, s["tp1"], s["tp2"], s["tp3"],
                                 status, high=float(c["high"]), low=float(c["low"]))
            if not res:
                continue
            new = res["status"]
            if new in ("TP3_HIT", "SL_HIT"):
                return self.classify(new, status), c["timestamp"].isoformat()
            status = new
            if res.get("sl") is not None:
                sl = res["sl"]
        return "EXPIRED", None

    def test_random_paths_match_production_state_machine(self):
        rng = np.random.default_rng(2026)
        mismatches = []
        n_term = 0
        for i in range(600):
            d = "LONG" if i % 2 == 0 else "SHORT"
            s = sig(d)
            p = 100.0 + np.cumsum(rng.normal(0, 0.9, 60))
            rows = [(max(p[k], p[k - 1] if k else 100) + rng.uniform(0, .8), min(p[k], p[k - 1] if k else 100) - rng.uniform(0, .8)) for k in range(60)]
            df = candles(rows)
            out = historical_outcome(s, df)
            exp, when = self._walk(s, df)
            if exp != "EXPIRED":
                n_term += 1
            if out["status"] != exp or (exp != "EXPIRED" and out.get("event_time") != when):
                mismatches.append((i, d, out["status"], exp))
        self.assertGreater(n_term, 200, "paths too tame to be a meaningful differential test")
        self.assertEqual(mismatches, [], mismatches[:5])

    def test_long_short_are_exact_mirrors(self):
        rng = np.random.default_rng(7)
        for i in range(400):
            p = 100.0 + np.cumsum(rng.normal(0, 0.9, 60))
            rows = [(max(p[k], p[k - 1] if k else 100) + rng.uniform(0, .8), min(p[k], p[k - 1] if k else 100) - rng.uniform(0, .8)) for k in range(60)]
            long_out = historical_outcome(sig("LONG"), candles(rows))
            mirrored = [(200.0 - l, 200.0 - h) for h, l in rows]
            short_out = historical_outcome(sig("SHORT"), candles(mirrored))
            self.assertEqual((long_out["status"], long_out.get("event_time"), long_out.get("milestones")),
                             (short_out["status"], short_out.get("event_time"), short_out.get("milestones")), i)


if __name__ == "__main__":
    unittest.main()
