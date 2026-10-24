"""Opt-in final-entry integrity for the RRCE contract (default OFF).

Context (Run #68, 54 RRCE-contract signals): the 4R cap is applied to the PLANNED
target at the planned entry; rebasing the entry to the live price can shrink the
stop distance, so the final RR reached 56.7R and 7 signals had stops < 0.3%
(down to 0.013%). The ATR contract enforces min_sl_pct; the RRCE path enforced
nothing equivalent. The new bounds are opt-in and must not alter default behaviour.
"""
import itertools
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from engines.rrce_engine import RRCEEngine  # noqa: E402
from engines.live_entry_integrity import revalidate  # noqa: E402


def reference_live_entry_levels(direction, live_price, stage4, max_deviation_pct, min_rr):
    """Verbatim pre-change logic (golden reference for backward compatibility)."""
    if not stage4:
        return {"valid": False, "reason": "missing_stage4"}
    if stage4.get("valid") is not True:
        return {"valid": False, "reason": "invalid_stage4"}
    planned_entry = float(stage4["entry"]); sl = float(stage4["sl"]); tp = float(stage4["tp"])
    if planned_entry <= 0 or live_price <= 0:
        return {"valid": False, "reason": "invalid_price"}
    deviation_pct = abs(live_price - planned_entry) / planned_entry * 100
    if deviation_pct > max_deviation_pct:
        return {"valid": False, "reason": "price_away_from_rrce_entry", "planned_entry": planned_entry,
                "deviation_pct": round(deviation_pct, 3)}
    if direction == "LONG":
        ok = sl < live_price < tp
    elif direction == "SHORT":
        ok = tp < live_price < sl
    else:
        return {"valid": False, "reason": "invalid_direction"}
    if not ok:
        return {"valid": False, "reason": "invalid_live_structure"}
    risk = abs(live_price - sl); reward = abs(tp - live_price)
    rr = reward / risk if risk else 0.0
    if rr < min_rr:
        return {"valid": False, "reason": "rr_below_minimum", "rr": round(rr, 2)}
    return {"valid": True, "entry": live_price, "sl": sl, "tp1": tp, "tp2": tp, "tp3": tp, "rr": round(rr, 2),
            "planned_entry": planned_entry, "deviation_pct": round(deviation_pct, 3)}


def stage4(direction, entry=100.0, stop_pct=1.0, rr=3.0):
    risk = entry * stop_pct / 100
    if direction == "LONG":
        return {"valid": True, "entry": entry, "sl": entry - risk, "tp": entry + rr * risk}
    return {"valid": True, "entry": entry, "sl": entry + risk, "tp": entry - rr * risk}


class BackwardCompatibilityTests(unittest.TestCase):
    def test_disabled_bounds_are_identical_to_previous_behaviour(self):
        n = 0
        for d, live, stop_pct, rr in itertools.product(
                ("LONG", "SHORT"), (99.0, 99.6, 99.9, 100.0, 100.1, 100.4, 101.0, 95.0, 105.0, -1.0),
                (0.01, 0.2, 0.3, 1.0, 3.0), (1.2, 2.0, 3.0, 4.0, 6.0)):
            s4 = stage4(d, stop_pct=stop_pct, rr=rr)
            for kw in ({}, {"max_rr": None, "min_stop_pct": None}):
                got = RRCEEngine.live_entry_levels(d, live, s4, 0.4, 2.0, **kw)
                self.assertEqual(got, reference_live_entry_levels(d, live, s4, 0.4, 2.0), (d, live, stop_pct, rr, kw))
                n += 1
        self.assertGreater(n, 500)
        for bad in (None, {}, {"valid": False}):
            self.assertEqual(RRCEEngine.live_entry_levels("LONG", 100.0, bad, 0.4, 2.0),
                             reference_live_entry_levels("LONG", 100.0, bad, 0.4, 2.0))

    def test_config_defaults_are_disabled(self):
        from config import CONFIG
        self.assertIsNone(CONFIG["rrce_final_max_rr"])
        self.assertIsNone(CONFIG["rrce_min_stop_pct"])


class BoundsTests(unittest.TestCase):
    def test_final_rr_can_exceed_planned_cap_when_live_price_nears_stop(self):
        """Demonstrates the gap: planned RR 3.0 (<= 4 cap) becomes ~19R after the live rebase."""
        s4 = stage4("LONG", stop_pct=1.0, rr=3.0)               # sl 99.0, tp 103.0
        out = RRCEEngine.live_entry_levels("LONG", 99.2, s4, 0.8, 2.0)   # within 0.8% deviation
        self.assertTrue(out["valid"])
        self.assertGreater(out["rr"], 15.0)

    def test_max_rr_boundary_long_short(self):
        for d in ("LONG", "SHORT"):
            s4 = stage4(d, stop_pct=1.0, rr=4.0)
            at_cap = RRCEEngine.live_entry_levels(d, 100.0, s4, 0.4, 2.0, max_rr=4.0)
            self.assertTrue(at_cap["valid"], d)                                   # RR == cap passes
            near = 99.4 if d == "LONG" else 100.6                                 # moves live price toward the stop
            over = RRCEEngine.live_entry_levels(d, near, s4, 0.8, 2.0, max_rr=4.0)
            self.assertEqual((over["valid"], over.get("reason")), (False, "rr_above_maximum"), d)

    def test_min_stop_boundary_long_short(self):
        for d in ("LONG", "SHORT"):
            # float noise makes the exact boundary meaningless; test both sides with margin
            ok = RRCEEngine.live_entry_levels(d, 100.0, stage4(d, stop_pct=0.3001, rr=3.0), 0.4, 2.0, min_stop_pct=0.3)
            self.assertTrue(ok["valid"], d)
            just_below = RRCEEngine.live_entry_levels(d, 100.0, stage4(d, stop_pct=0.2999, rr=3.0), 0.4, 2.0, min_stop_pct=0.3)
            self.assertEqual(just_below["reason"], "stop_distance_below_minimum", d)
            tiny = RRCEEngine.live_entry_levels(d, 100.0, stage4(d, stop_pct=0.013, rr=3.0), 0.4, 2.0, min_stop_pct=0.3)
            self.assertEqual((tiny["valid"], tiny["reason"]), (False, "stop_distance_below_minimum"), d)

    def test_tiny_stop_reports_stop_reason_not_rr_reason(self):
        out = RRCEEngine.live_entry_levels("LONG", 100.0, stage4("LONG", stop_pct=0.02, rr=40.0), 0.4, 2.0,
                                           max_rr=4.0, min_stop_pct=0.3)
        self.assertEqual(out["reason"], "stop_distance_below_minimum")

    def test_other_rejections_take_precedence_and_unchanged(self):
        s4 = stage4("LONG")
        self.assertEqual(RRCEEngine.live_entry_levels("LONG", 103.0, s4, 0.4, 2.0, max_rr=4.0, min_stop_pct=0.3)["reason"],
                         "price_away_from_rrce_entry")
        self.assertEqual(RRCEEngine.live_entry_levels("LONG", 98.0, s4, 5.0, 2.0, max_rr=4.0, min_stop_pct=0.3)["reason"],
                         "invalid_live_structure")

    def test_wrapper_passes_bounds_and_keeps_ladder(self):
        eng = RRCEEngine()
        ok = revalidate(eng, "LONG", 100.0, stage4("LONG", stop_pct=1.0, rr=3.0), 0.4, 2.0, max_rr=4.0, min_stop_pct=0.3)
        self.assertTrue(ok["valid"])
        for k in ("tp1", "tp2", "tp3"):
            self.assertIn(k, ok)
        rej = revalidate(eng, "LONG", 100.0, stage4("LONG", stop_pct=0.1, rr=3.0), 0.4, 2.0, min_stop_pct=0.3)
        self.assertEqual(rej["reason"], "stop_distance_below_minimum")


if __name__ == "__main__":
    unittest.main()


class LegacyInterfaceCompatibilityTests(unittest.TestCase):
    def test_disabled_bounds_do_not_reach_engines_with_the_original_signature(self):
        class OldEngine:  # implements only the original interface
            @staticmethod
            def live_entry_levels(direction, live_price, stage4, max_deviation_pct, min_rr):
                return {"valid": True, "entry": live_price, "tp3": stage4["tp"], "sl": stage4["sl"], "rr": 3.0}
        out = revalidate(OldEngine(), "LONG", 100.0, stage4("LONG"), 0.4, 2.0)
        self.assertTrue(out["valid"])
