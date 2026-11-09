import unittest

from tools.rrce_aligned_short_analysis import (
    build_report,
    chronological_split,
    outcome_counts,
)


class RRCEAlignedShortAnalysisTests(unittest.TestCase):
    def test_outcome_counts_excludes_expired_from_resolved_rate(self):
        rows = [
            {"outcome": "TP3_HIT"},
            {"outcome": "SL_HIT"},
            {"outcome": "EXPIRED"},
        ]
        result = outcome_counts(rows)
        self.assertEqual(result["resolved"], 2)
        self.assertEqual(result["tp3_rate_pct"], 50.0)
        self.assertEqual(result["expired"], 1)

    def test_chronological_split_keeps_latest_rows_as_holdout(self):
        rows = [{"replay_time": f"2026-01-{day:02d}T00:00:00Z"} for day in range(1, 7)]
        discovery, holdout = chronological_split(rows)
        self.assertEqual(discovery[-1]["replay_time"], "2026-01-04T00:00:00Z")
        self.assertEqual(holdout[0]["replay_time"], "2026-01-05T00:00:00Z")

    def test_rrce_qualified_cohort_is_separate_from_failed_stages(self):
        payload = {"results": [
            {"direction": "SHORT", "rrce_status": "QUALIFIED",
             "rrce_failed_stage": None, "rrce_choch_confirmed": True,
             "outcome": "SL_HIT", "replay_time": "2026-01-01T00:00:00Z",
             "symbol": "BTC", "entry": 100, "sl": 102, "tp3": 96},
            {"direction": "SHORT", "rrce_status": "NONQUALIFYING",
             "rrce_failed_stage": "stage3_confirmation", "rrce_choch_confirmed": False,
             "outcome": "TP3_HIT", "replay_time": "2026-01-02T00:00:00Z",
             "symbol": "ETH", "entry": 100, "sl": 102, "tp3": 96},
            {"direction": "LONG", "rrce_status": "QUALIFIED", "outcome": "TP3_HIT"},
        ]}
        report = build_report(payload)
        self.assertEqual(report["baseline"]["signals"], 2)
        self.assertEqual(report["rrce_status_cohorts"]["QUALIFIED"]["sl"], 1)
        self.assertEqual(report["rrce_failed_stage_cohorts"]["stage3_confirmation"]["tp3"], 1)
        self.assertFalse(report["production_strategy_changed"])


if __context__ := True:
    pass
