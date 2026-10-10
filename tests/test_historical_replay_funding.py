"""Regression tests for historical funding archive loading and causality."""

import unittest
from unittest import mock

import pandas as pd

from tools import historical_replay as replay


def ms(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


class HistoricalFundingArchiveTests(unittest.TestCase):
    def test_fetches_monthly_archives_and_filters_exact_window(self):
        start_ms = ms("2026-09-30 00:00:00")
        end_ms = ms("2026-10-01 00:00:00")
        september = pd.DataFrame(
            {
                "calc_time": [
                    "2026-09-29 23:59:00",
                    "2026-09-30 00:00:00",
                    "2026-10-01 00:00:00",
                ],
                "last_funding_rate": [0.001, 0.002, 0.003],
            }
        )
        october = pd.DataFrame(
            {
                "calc_time": [
                    "2026-10-01 00:00:00",
                    "2026-10-02 00:00:00",
                ],
                "last_funding_rate": [0.003, 0.004],
            }
        )

        with mock.patch.object(
            replay, "_download_archive_csv", side_effect=[september, october]
        ) as download:
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(
            [call.args[0] for call in download.call_args_list],
            [
                "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                "ETHUSDT/ETHUSDT-fundingRate-2026-09.zip",
                "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                "ETHUSDT/ETHUSDT-fundingRate-2026-10.zip",
            ],
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(
            list(result["timestamp"]),
            [
                pd.Timestamp("2026-09-30 00:00:00", tz="UTC"),
                pd.Timestamp("2026-10-01 00:00:00", tz="UTC"),
            ],
        )
        self.assertEqual(list(result["fundingRate"]), [0.002, 0.003])

    def test_parses_epoch_millisecond_funding_timestamps(self):
        start_ms = ms("2026-09-01 00:00:00")
        end_ms = ms("2026-09-02 00:00:00")
        frame = pd.DataFrame(
            {
                "fundingTime": [start_ms, end_ms + 60_000],
                "fundingRate": [0.0015, 0.0025],
            }
        )

        with mock.patch.object(replay, "_download_archive_csv", return_value=frame):
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["timestamp"], pd.Timestamp(start_ms, unit="ms", tz="UTC"))
        self.assertEqual(result.iloc[0]["fundingRate"], 0.0015)

    def test_empty_or_unrecognized_archives_return_empty_schema(self):
        start_ms = ms("2026-09-01 00:00:00")
        end_ms = ms("2026-09-02 00:00:00")
        with mock.patch.object(
            replay, "_download_archive_csv", return_value=pd.DataFrame({"unexpected": [1]})
        ):
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(list(result.columns), ["timestamp", "fundingRate"])
        self.assertTrue(result.empty)




class HistoricalOutcomeAccountingTests(unittest.TestCase):
    def _signal(self, direction="LONG"):
        return {
            "direction": direction,
            "entry": 100.0,
            "sl": 95.0 if direction == "LONG" else 105.0,
            "tp1": 105.0 if direction == "LONG" else 95.0,
            "tp2": 110.0 if direction == "LONG" else 90.0,
            "tp3": 115.0 if direction == "LONG" else 85.0,
            "_replay_time": "2026-09-01T00:00:00+00:00",
        }

    def _candles(self, first_high, first_low, second_high, second_low):
        return pd.DataFrame([
            {"timestamp": pd.Timestamp("2026-09-01T00:05:00Z"), "high": first_high, "low": first_low},
            {"timestamp": pd.Timestamp("2026-09-01T00:10:00Z"), "high": second_high, "low": second_low},
        ])

    def test_long_stop_after_tp1_is_not_counted_as_full_sl(self):
        result = replay.historical_outcome(
            self._signal("LONG"), self._candles(106.0, 101.0, 103.0, 99.0)
        )
        self.assertEqual(result["status"], "BREAKEVEN_AFTER_TP1")
        self.assertEqual(result["milestones"], ["TP1"])

    def test_long_stop_after_tp2_is_not_counted_as_full_sl(self):
        result = replay.historical_outcome(
            self._signal("LONG"), self._candles(111.0, 101.0, 103.0, 99.0)
        )
        self.assertEqual(result["status"], "BREAKEVEN_AFTER_TP2")
        self.assertEqual(result["milestones"], ["TP1", "TP2"])

    def test_short_stop_after_tp1_is_not_counted_as_full_sl(self):
        result = replay.historical_outcome(
            self._signal("SHORT"), self._candles(99.0, 94.0, 101.0, 97.0)
        )
        self.assertEqual(result["status"], "BREAKEVEN_AFTER_TP1")
        self.assertEqual(result["milestones"], ["TP1"])

    def test_stop_before_any_target_remains_sl_hit(self):
        result = replay.historical_outcome(
            self._signal("LONG"), self._candles(102.0, 94.0, 103.0, 99.0)
        )
        self.assertEqual(result["status"], "SL_HIT")
        self.assertEqual(result["milestones"], [])

    def test_tp3_same_candle_records_all_crossed_milestones_long_and_short(self):
        long_result = replay.historical_outcome(
            self._signal("LONG"), self._candles(116.0, 101.0, 103.0, 99.0)
        )
        short_result = replay.historical_outcome(
            self._signal("SHORT"), self._candles(99.0, 84.0, 101.0, 97.0)
        )
        self.assertEqual(long_result["status"], "TP3_HIT")
        self.assertEqual(long_result["milestones"], ["TP1", "TP2"])
        self.assertEqual(short_result["status"], "TP3_HIT")
        self.assertEqual(short_result["milestones"], ["TP1", "TP2"])

    def test_tp3_after_tp1_records_intermediate_tp2(self):
        result = replay.historical_outcome(
            self._signal("LONG"), self._candles(106.0, 101.0, 116.0, 101.0)
        )
        self.assertEqual(result["status"], "TP3_HIT")
        self.assertEqual(result["milestones"], ["TP1", "TP2"])

    def test_summary_counts_breakeven_exits_separately(self):
        rows = [
            {"outcome": "TP3_HIT", "rrce_status": "QUALIFIED"},
            {"outcome": "SL_HIT", "rrce_status": "NONQUALIFYING"},
            {"outcome": "BREAKEVEN_AFTER_TP1", "rrce_status": "NONQUALIFYING"},
            {"outcome": "BREAKEVEN_AFTER_TP2", "rrce_status": "NONQUALIFYING"},
            {"outcome": "EXPIRED", "rrce_status": "NONQUALIFYING"},
        ]
        summary = replay.summarize(rows)
        self.assertEqual(summary["resolved"], 4)
        self.assertEqual(summary["tp"], 1)
        self.assertEqual(summary["sl"], 1)
        self.assertEqual(summary["breakeven_after_tp1"], 1)
        self.assertEqual(summary["breakeven_after_tp2"], 1)
        self.assertEqual(summary["breakeven_exits"], 2)



class ReplayCooldownTests(unittest.TestCase):
    def test_cooldown_uses_replay_time_and_expires_at_configured_boundary(self):
        cooldown = replay.ReplayCooldown(4)
        cooldown.advance(pd.Timestamp("2026-09-01T12:00:00Z"))
        self.assertFalse(cooldown.is_on_cooldown("ETHUSDT"))
        cooldown.set_cooldown("ETHUSDT")

        cooldown.advance(pd.Timestamp("2026-09-01T15:59:00Z"))
        self.assertTrue(cooldown.is_on_cooldown("ETHUSDT"))
        self.assertFalse(cooldown.is_on_cooldown("SOLUSDT"))

        cooldown.advance(pd.Timestamp("2026-09-01T16:00:00Z"))
        self.assertFalse(cooldown.is_on_cooldown("ETHUSDT"))

    def test_cooldown_does_not_depend_on_wall_clock(self):
        cooldown = replay.ReplayCooldown(4)
        cooldown.advance(pd.Timestamp("2020-01-01T00:00:00Z"))
        cooldown.set_cooldown("ETHUSDT")
        cooldown.advance(pd.Timestamp("2020-01-01T03:00:00Z"))
        self.assertTrue(cooldown.is_on_cooldown("ETHUSDT"))

if __name__ == "__main__":
    unittest.main()
