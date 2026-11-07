import csv
import tempfile
import unittest
from pathlib import Path

from research.indicator_counterfactual import (
    at_least,
    chronological_windows,
    metrics,
    window_report,
    number,
    resolved_rows,
)


class IndicatorCounterfactualTests(unittest.TestCase):
    def test_number_handles_missing_invalid_and_non_finite_values(self):
        self.assertIsNone(number({}, "rsi"))
        self.assertIsNone(number({"rsi": "not-a-number"}, "rsi"))
        self.assertIsNone(number({"rsi": "nan"}, "rsi"))
        self.assertIsNone(number({"rsi": "inf"}, "rsi"))
        self.assertEqual(number({"rsi": "50.5"}, "rsi"), 50.5)

    def test_at_least_requires_a_valid_value_and_includes_threshold(self):
        self.assertTrue(at_least({"adx": "20"}, "adx", 20))
        self.assertFalse(at_least({"adx": "19.99"}, "adx", 20))
        self.assertFalse(at_least({}, "adx", 20))

    def test_resolved_rows_filters_outcomes_and_sorts_chronologically(self):
        rows = [
            {"timestamp": "2026-01-03T00:00:00Z", "status": "SL_HIT", "direction": "SHORT"},
            {"timestamp": "2026-01-01T00:00:00Z", "status": "OPEN", "direction": "LONG"},
            {"timestamp": "2026-01-02T00:00:00Z", "status": "TP3_HIT", "direction": "SHORT"},
            {"timestamp": "", "status": "TP3_HIT", "direction": "LONG"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["timestamp", "status", "direction"])
                writer.writeheader()
                writer.writerows(rows)
            result = resolved_rows(path)

        self.assertEqual([row["timestamp"] for row in result], [
            "2026-01-02T00:00:00Z",
            "2026-01-03T00:00:00Z",
        ])

    def test_chronological_windows_are_contiguous_and_cover_all_rows(self):
        rows = [{"timestamp": f"2026-01-{i:02d}", "status": "SL_HIT"} for i in range(1, 12)]
        windows = chronological_windows(rows, 5)
        self.assertEqual([len(w) for w in windows], [3, 2, 2, 2, 2])
        self.assertEqual([r["timestamp"] for w in windows for r in w],
                         [r["timestamp"] for r in rows])
        self.assertEqual(windows[0][0]["timestamp"], "2026-01-01")
        self.assertEqual(windows[-1][-1]["timestamp"], "2026-01-11")

    def test_chronological_windows_reject_invalid_sizes(self):
        with self.assertRaises(ValueError):
            chronological_windows([], 5)
        with self.assertRaises(ValueError):
            chronological_windows([{"timestamp": "x"}], 1)

    def test_window_report_includes_candidate_delta_and_sample_sizes(self):
        rows = []
        for i in range(1, 11):
            rows.append({
                "timestamp": f"2026-01-{i:02d}",
                "status": "TP3_HIT" if i % 2 == 0 else "SL_HIT",
                "direction": "SHORT",
                "rsi": "55",
                "adx": "25",
            })
        report = window_report(rows, [
            ("SHORT baseline", lambda r: r.get("direction") == "SHORT"),
            ("SHORT RSI >= 50 AND ADX >= 20",
             lambda r: r.get("direction") == "SHORT" and at_least(r, "rsi", 50)
             and at_least(r, "adx", 20)),
        ], 2)
        self.assertEqual(len(report), 2)
        self.assertEqual(report[0]["candidate_vs_short_baseline"]["candidate_n"], 5)
        self.assertEqual(report[0]["candidate_vs_short_baseline"]["tp3_rate_delta_pp"], 0.0)

    def test_metrics_empty_and_non_empty(self):
        self.assertEqual(
            metrics([]),
            {"n": 0, "tp3": 0, "sl": 0, "tp3_rate_pct": None},
        )
        self.assertEqual(
            metrics([
                {"status": "TP3_HIT"},
                {"status": "SL_HIT"},
                {"status": "TP3_HIT"},
            ]),
            {"n": 3, "tp3": 2, "sl": 1, "tp3_rate_pct": 66.67},
        )


if __name__ == "__main__":
    unittest.main()
