"""OI replay fixtures (v2): numeric + no-future-leakage checks against a production-semantics oracle.

The fixture script lives in tests/fixtures/oi_fixtures_v2.py. This wrapper (1) requires the tree's own
replay harness to pass every fixture and every leakage test, and (2) proves the leakage tests are not
vacuous by running the same script against a copy of the harness with a deliberate future leak.
Production code is not touched.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "fixtures" / "oi_fixtures_v2.py"


def run_fixtures(root: Path, label: str, *flags: str):
    env = dict(os.environ, OI_OUT_DIR=tempfile.mkdtemp(), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, str(SCRIPT), str(root), label, *flags], capture_output=True, text=True,
                       env=env, cwd=str(root), timeout=240)
    return p.returncode, p.stdout + p.stderr


class OiReplayFixtureTests(unittest.TestCase):
    def test_tree_harness_matches_oracle_and_has_no_future_leakage(self):
        code, out = run_fixtures(ROOT, "tree", "--strict-oracle")
        self.assertEqual(code, 0, out[-2500:])
        self.assertIn("44 fixtures", out)
        self.assertIn("label mismatches 0 | price mismatches (>0.001) 0 | OI mismatches (>0.005) 0 | fully matching 44", out)
        self.assertEqual(out.count("FAIL"), 0, out)
        for c in ("C1", "C2", "C2b", "C4", "C5", "C6", "C7"):
            self.assertIn(f"PASS  {c} ", out)

    def test_leakage_tests_detect_a_deliberate_future_leak(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            dst = tmp / "tree"
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "storage", "research", ".pytest_cache"))
            p = dst / "tools" / "historical_replay.py"
            src = p.read_text()
            old = '        past = df[df["timestamp"] <= self.store.end]\n        if past.empty:\n            return {}\n        return {"openInterestValue"'
            self.assertEqual(src.count(old), 1, "harness changed: update the mutation")
            p.write_text(src.replace(old, '        past = df  # MUTANT: reads future observations\n        if past.empty:\n            return {}\n        return {"openInterestValue"'))
            code, out = run_fixtures(dst, "mutant")
            self.assertEqual(code, 1, out[-2000:])
            for c in ("C1", "C2", "C5"):
                self.assertIn(f"FAIL  {c} ", out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
