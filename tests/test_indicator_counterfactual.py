import csv
import tempfile
import unittest
from pathlib import Path

from research.indicator_counterfactual import (
    at_least,
    metrics,
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
