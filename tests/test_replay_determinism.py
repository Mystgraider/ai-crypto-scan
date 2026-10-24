"""Record-level determinism of the historical replay for a fixed window.

An aggregate-summary match is not sufficient evidence of reproducibility. This
compares every field of every signal row (identity, levels, score, grade, RRCE
state, outcome, event_time, milestones) between independent replays of the same
frozen inputs: twice in-process and once in a fresh interpreter process with a
different PYTHONHASHSEED.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from test_historical_replay_sink_regression import synthetic_store  # noqa: E402

import tools.historical_replay as hr  # noqa: E402

END = "2026-10-01T12:00:00Z"
REPO = Path(__file__).resolve().parents[1]
CHILD = r'''
import json, os, sys, tempfile
from pathlib import Path
from unittest import mock
sys.path.insert(0, %(repo)r); sys.path.insert(0, %(tests)r)
import pandas as pd
from test_historical_replay_sink_regression import synthetic_store
import tools.historical_replay as hr
store = synthetic_store(pd.Timestamp(%(end)r))
d = tempfile.mkdtemp(); os.makedirs(d + "/storage"); os.chdir(d)
out = Path(d) / "r.json"
os.environ["BACKTEST_END"] = %(end)r
with mock.patch.object(hr, "DAYS", 6 / 24), mock.patch.object(hr, "load_store", lambda s, e: store), mock.patch.object(hr, "RESULTS", out):
    hr.run()
Path(%(dest)r).write_text(out.read_text())
'''


def _inprocess():
    store = synthetic_store(pd.Timestamp(END))
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "storage"))
        out = Path(tmp) / "r.json"
        os.chdir(tmp)
        try:
            with mock.patch.object(hr, "DAYS", 6 / 24), mock.patch.object(hr, "load_store", lambda s, e: store), \
                 mock.patch.object(hr, "RESULTS", out), mock.patch.dict(os.environ, {"BACKTEST_END": END}):
                hr.run()
        finally:
            os.chdir(cwd)
        return json.loads(out.read_text())


def _stable_meta(m):
    return {k: v for k, v in m.items() if k != "generated_at"}  # wall-clock stamp only


def row_diffs(a, b):
    ka = {(r["replay_time"], r["symbol"], r["direction"]): r for r in a}
    kb = {(r["replay_time"], r["symbol"], r["direction"]): r for r in b}
    diffs = [("only_in_a", k) for k in ka.keys() - kb.keys()] + [("only_in_b", k) for k in kb.keys() - ka.keys()]
    for k in ka.keys() & kb.keys():
        for f in ka[k]:
            if ka[k][f] != kb[k].get(f) and not (ka[k][f] != ka[k][f] and kb[k].get(f) != kb[k].get(f)):  # NaN == NaN
                diffs.append((k, f, ka[k][f], kb[k].get(f)))
    return diffs


class ReplayDeterminismTests(unittest.TestCase):
    def test_fixed_window_is_record_level_deterministic(self):
        r1, r2 = _inprocess(), _inprocess()
        self.assertGreater(len(r1["results"]), 0, "no signals; determinism test would be vacuous")
        self.assertTrue(r1["metadata"]["fixed_window"])
        self.assertEqual(r1["metadata"]["end"], pd.Timestamp(END).isoformat())
        self.assertEqual(row_diffs(r1["results"], r2["results"]), [])
        self.assertEqual(r1["summary"], r2["summary"])
        self.assertEqual(_stable_meta(r1["metadata"]), _stable_meta(r2["metadata"]))
        self.assertEqual([r["replay_time"] for r in r1["results"]], [r["replay_time"] for r in r2["results"]])  # order too

    def test_fresh_process_with_different_hash_seed_matches(self):
        r1 = _inprocess()
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "child.json")
            code = CHILD % {"repo": str(REPO), "tests": os.path.dirname(__file__), "end": END, "dest": dest}
            env = dict(os.environ, PYTHONHASHSEED="12345")
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=240)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            child = json.loads(Path(dest).read_text())
        self.assertEqual(row_diffs(r1["results"], child["results"]), [])
        self.assertEqual(r1["summary"], child["summary"])

    def test_rolling_default_unchanged_without_env(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BACKTEST_END", None)
            now = pd.Timestamp("2026-10-11T07:42:13Z")
            self.assertEqual(hr.resolve_replay_end(now), pd.Timestamp("2026-10-11T06:00:00Z"))

    def test_fixed_window_rejects_non_hour_boundaries(self):
        with mock.patch.dict(os.environ, {"BACKTEST_END": "2026-10-01T12:30:00Z"}):
            with self.assertRaises(ValueError):
                hr.resolve_replay_end()


if __name__ == "__main__":
    unittest.main()
