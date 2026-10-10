"""Regression: when an RRCE-valid candidate cannot fetch its live ticker, the
scanner must fall back to the ATR contract (as the in-code comment states:
'RRCE cannot collapse signal volume to zero'). Before the fix, rrce_risk was set
to None and then dereferenced (rrce_risk.get) -> AttributeError -> the candidate
was silently dropped by the per-symbol exception handler."""
import os
import sys
import tempfile
import json
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from test_historical_replay_sink_regression import synthetic_store  # noqa: E402

import tools.historical_replay as hr  # noqa: E402
from engines.rrce_engine import RRCEEngine  # noqa: E402


def _run_replay(store, fake_rrce_valid_with_ticker_failure):
    state = {"pending": False, "failures": 0}
    orig_eval = RRCEEngine.evaluate
    orig_ticker = hr.ReplayExchange.fetch_ticker

    def fake_eval(self, *a, **k):
        real = orig_eval(self, *a, **k)
        price = float(k.get("price", a[5] if len(a) > 5 else 100.0))
        direction = k.get("direction")
        step = price * 0.01
        if direction == "LONG":
            stage4 = {"valid": True, "entry": price, "sl": price - step, "tp": price + 3 * step, "rr": 3.0}
        else:
            stage4 = {"valid": True, "entry": price, "sl": price + step, "tp": price - 3 * step, "rr": 3.0}
        state["pending"] = True
        return {"valid": True, "failed_at": None, "bonus": 0.0, "stage1": {"passed": True},
                "stage2": {"passed": True}, "stage3": {"passed": True}, "stage4": stage4}

    def flaky_ticker(self, symbol):
        if state["pending"]:
            state["pending"] = False
            state["failures"] += 1
            raise RuntimeError("simulated ticker outage")
        return orig_ticker(self, symbol)

    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "storage"), exist_ok=True)
        out = Path(tmp) / "r.json"
        os.chdir(tmp)
        try:
            patches = [mock.patch.object(hr, "DAYS", 6 / 24), mock.patch.object(hr, "load_store", lambda s, e: store),
                       mock.patch.object(hr, "RESULTS", out),
                       mock.patch.dict(os.environ, {"BACKTEST_END": "2026-10-01T12:00:00Z"})]
            if fake_rrce_valid_with_ticker_failure:
                patches += [mock.patch.object(RRCEEngine, "evaluate", fake_eval),
                            mock.patch.object(hr.ReplayExchange, "fetch_ticker", flaky_ticker)]
            for p in patches:
                p.start()
            try:
                hr.run()
            finally:
                for p in reversed(patches):
                    p.stop()
        finally:
            os.chdir(cwd)
        rows = json.loads(out.read_text())["results"]
    return rows, state["failures"]


class RrceLivePriceFallbackTests(unittest.TestCase):
    def test_ticker_outage_for_rrce_valid_candidate_falls_back_to_atr(self):
        end = pd.Timestamp("2026-10-01T12:00:00Z")
        store = synthetic_store(end)
        baseline, _ = _run_replay(store, False)
        self.assertGreater(len(baseline), 0, "synthetic replay produced no signals; test would be vacuous")
        faulted, failures = _run_replay(synthetic_store(end), True)
        self.assertGreater(failures, 0, "fault was never injected")
        self.assertEqual(len(faulted), len(baseline),
                         f"candidates lost on ticker outage: baseline={len(baseline)} faulted={len(faulted)}")
        self.assertTrue(all(r["rrce_risk_contract"] == "ATR_FALLBACK" for r in faulted))


if __name__ == "__main__":
    unittest.main()
