"""End-to-end (real scanner_v5.main via the replay harness): the opt-in bounds are
wired at both live-validation call sites, fall back to ATR instead of dropping the
candidate, are reported in telemetry, and never leak out of the research run."""
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from test_rrce_live_price_fallback import _run_replay  # noqa: E402
from test_historical_replay_sink_regression import synthetic_store  # noqa: E402
from config import CONFIG  # noqa: E402

END = pd.Timestamp("2026-10-01T12:00:00Z")


class RrceFinalEntryIntegrityReplayTests(unittest.TestCase):
    def _rows(self, env):
        with mock.patch.dict(os.environ, env):
            return _run_replay(synthetic_store(END), True, ticker_failure=False)[0]

    def test_default_off_uses_rrce_contract_and_overrides_do_not_leak(self):
        rows = self._rows({})
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(r["rrce_risk_contract"] == "RRCE" for r in rows))
        self.assertIsNone(CONFIG["rrce_final_max_rr"])
        self.assertIsNone(CONFIG["rrce_min_stop_pct"])

    def test_bounds_demote_to_atr_fallback_with_reason_and_keep_signal_count(self):
        base = self._rows({})
        stop = self._rows({"RRCE_MIN_STOP_PCT": "2.0"})       # fake planned stop is 1%
        cap = self._rows({"RRCE_FINAL_MAX_RR": "2.5"})        # fake planned RR is 3.0
        for rows, reason in ((stop, "stop_distance_below_minimum"), (cap, "rr_above_maximum")):
            self.assertEqual(len(rows), len(base), reason)   # fallback preserves the candidate
            self.assertTrue(all(r["rrce_risk_contract"] == "ATR_FALLBACK" for r in rows), reason)
            self.assertTrue(all(r["rrce_failure_reason"] == reason for r in rows), reason)
        self.assertIsNone(CONFIG["rrce_final_max_rr"])
        self.assertIsNone(CONFIG["rrce_min_stop_pct"])

    def test_bounds_that_are_satisfied_change_nothing(self):
        base = self._rows({})
        same = self._rows({"RRCE_MIN_STOP_PCT": "0.5", "RRCE_FINAL_MAX_RR": "4.0"})
        key = lambda r: (r["replay_time"], r["symbol"], r["direction"], r["entry"], r["sl"], r["tp3"], r["rrce_risk_contract"])
        self.assertEqual(sorted(map(key, base)), sorted(map(key, same)))


if __name__ == "__main__":
    unittest.main()
