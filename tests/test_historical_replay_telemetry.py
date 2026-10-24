"""Regression tests for observation-only replay candidate telemetry capture."""

import unittest

from tools.historical_replay import ReplayTelemetryRanker, merge_replay_telemetry


class ReplayTelemetryCaptureTests(unittest.TestCase):
    def _candidate(self):
        return {
            "symbol": "SUI/USDT:USDT",
            "direction": "LONG",
            "trend_score": 71.25,
            "quality_score": 83.5,
            "rs_score": 66.0,
            "funding_pct_raw": -0.0012,
            "stoch_k": 54.2,
            "macd_hist": 0.012345,
            "bb_pct_b": 0.61,
            "mtf_4h": "BULLISH",
            "mtf_15m": "BULLISH",
            "rr": 2.5,
            "sr_bonus": 5.0,
            "grade": "B",
            "oi_signal": "CONFIRMED",
            "mtf_status": "CONFIRMED",
            "composite": 78.4,
        }

    def test_ranker_delegates_without_changing_candidate_or_rank_output(self):
        candidate = self._candidate()
        original = dict(candidate)
        sink = {}

        ranked = ReplayTelemetryRanker(sink).rank([candidate])

        self.assertEqual(candidate, original)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["composite"], original["composite"])
        self.assertIn("ai_rank_score", ranked[0])
        snapshot = dict(sink[("SUI/USDT:USDT", "LONG")][0])
        self.assertEqual(snapshot.pop("__composite"), 78.4)
        self.assertEqual(
            snapshot,
            {
                "trend_score": 71.25,
                "quality_score": 83.5,
                "rs_score": 66.0,
                "funding_pct_raw": -0.0012,
                "stoch_k": 54.2,
                "macd_hist": 0.012345,
                "bb_pct_b": 0.61,
                "mtf_4h": "BULLISH",
                "mtf_15m": "BULLISH",
            },
        )

    def test_merge_recovers_only_missing_fields(self):
        candidate = self._candidate()
        sink = {}
        ReplayTelemetryRanker(sink).rank([candidate])

        saved = {
            "symbol": candidate["symbol"],
            "direction": candidate["direction"],
            "score": candidate["composite"],
            "trend_score": 999.0,
        }
        merge_replay_telemetry(saved, sink)

        self.assertEqual(saved["trend_score"], 999.0)
        self.assertEqual(saved["quality_score"], 83.5)
        self.assertEqual(saved["rs_score"], 66.0)
        self.assertEqual(saved["funding_pct_raw"], -0.0012)
        self.assertEqual(saved["stoch_k"], 54.2)
        self.assertEqual(saved["macd_hist"], 0.012345)
        self.assertEqual(saved["bb_pct_b"], 0.61)
        self.assertEqual(saved["mtf_4h"], "BULLISH")
        self.assertEqual(saved["mtf_15m"], "BULLISH")

    def test_merge_raises_on_score_mismatch(self):
        candidate = self._candidate()
        sink = {}
        ReplayTelemetryRanker(sink).rank([candidate])

        saved = {
            "symbol": candidate["symbol"],
            "direction": candidate["direction"],
            "score": candidate["composite"] + 1.0,
        }
        with self.assertRaises(AssertionError):
            merge_replay_telemetry(saved, sink)

    def test_missing_snapshot_is_non_destructive(self):
        saved = {"symbol": "SUI/USDT:USDT", "direction": "LONG", "score": 78.4}
        merge_replay_telemetry(saved, {})
        self.assertEqual(saved, {
            "symbol": "SUI/USDT:USDT",
            "direction": "LONG",
            "score": 78.4,
        })


if __name__ == "__main__":
    unittest.main()
