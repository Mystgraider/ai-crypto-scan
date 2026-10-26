import unittest

from tools.rr_counterfactuals import run


def row(contract, entry, sl, tp3, outcome, milestones=(), t="2026-09-10T00:00:00+00:00"):
    return {"rrce_risk_contract": contract, "entry": entry, "sl": sl, "tp3": tp3, "outcome": outcome,
            "milestones": list(milestones), "replay_time": t}


class RrCounterfactualTests(unittest.TestCase):
    def test_groups_and_scope(self):
        rows = [
            row("RRCE", 100, 99, 103, "TP3_HIT"),                 # RR 3, stop 1%  -> retained
            row("RRCE", 100, 99.9, 108, "SL_HIT"),                # RR 80, stop 0.1% -> rejected by B and D
            row("RRCE", 100, 99.0, 106, "SL_HIT", ["TP1"]),       # RR 6 -> B only; counted as BE not SL
            row("ATR_FALLBACK", 100, 99.95, 106, "TP3_HIT"),      # out of scope even though RR 120
        ]
        rep = run(rows, split_ts="2026-09-11T00:00:00Z")
        cf = rep["counterfactuals"]
        self.assertEqual(cf["A_baseline"]["rejected"], 0)
        self.assertEqual(cf["B_reject_rr_above_max"]["rejected"], 2)
        self.assertEqual(cf["D_reject_stop_below_min"]["rejected"], 1)
        self.assertEqual(cf["E_reject_both"]["rejected"], 2)
        self.assertEqual(cf["B_reject_rr_above_max"]["rejected_outcomes_under_original_targets"]["BE"], 1)
        self.assertEqual(cf["A_baseline"]["retained_outcomes"]["TP3_over_TP3_plus_SL_pct"], 66.67)
        self.assertEqual(rep["level_audit"]["rrce_rows"], 3)
        self.assertIn("NOT VERIFIABLE", rep["option_C_adjust_target"])
        self.assertEqual(cf["A_baseline"]["development_before_split"]["retained_outcomes"]["n"], 4)

    def test_no_threshold_search_and_zero_risk_safe(self):
        rows = [row("RRCE", 100, 100, 103, "SL_HIT")]
        rep = run(rows)
        self.assertEqual(rep["level_audit"]["zero_risk_rows"], 1)


if __name__ == "__main__":
    unittest.main()
