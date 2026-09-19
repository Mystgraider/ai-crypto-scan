import unittest
import sys
import types

# Keep these tests runnable without pandas/numpy installed.
try:
    import pandas  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pandas"] = types.SimpleNamespace(DataFrame=object)

try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    sys.modules["numpy"] = types.SimpleNamespace()

from tracker.signal_tracker import SignalTracker


class SignalTrackerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tracker = SignalTracker.__new__(SignalTracker)

    def test_long_tp1_moves_to_open_tp1_and_breakeven(self):
        result = self.tracker._check(
            "LONG", 102.5, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN"
        )
        self.assertEqual(result, {"status": "OPEN_TP1", "sl": 100.0})

    def test_long_after_tp1_uses_breakeven_stop(self):
        result = self.tracker._check(
            "LONG", 99.9, 100.0, 100.0, 102.0, 104.0, 106.0, "OPEN_TP1"
        )
        self.assertEqual(result["status"], "SL_HIT")

    def test_long_tp2_keeps_signal_active(self):
        result = self.tracker._check(
            "LONG", 104.2, 100.0, 100.0, 102.0, 104.0, 106.0, "OPEN_TP1"
        )
        self.assertEqual(result["status"], "OPEN_TP2")

    def test_long_tp3_is_terminal(self):
        result = self.tracker._check(
            "LONG", 106.1, 100.0, 100.0, 102.0, 104.0, 106.0, "OPEN_TP2"
        )
        self.assertEqual(result["status"], "TP3_HIT")

    def test_long_direct_jump_to_tp3(self):
        result = self.tracker._check(
            "LONG", 108.0, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN"
        )
        self.assertEqual(result["status"], "TP3_HIT")

    def test_long_direct_jump_to_tp2(self):
        result = self.tracker._check(
            "LONG", 105.0, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN"
        )
        self.assertEqual(result, {"status": "OPEN_TP2", "sl": 100.0})

    def test_long_tp2_after_tp1_keeps_signal_active(self):
        result = self.tracker._check(
            "LONG", 104.0, 100.0, 100.0, 102.0, 104.0, 106.0, "OPEN_TP1"
        )
        self.assertEqual(result["status"], "OPEN_TP2")

    def test_long_tp2_then_breakeven_stop(self):
        result = self.tracker._check(
            "LONG", 99.9, 100.0, 100.0, 102.0, 104.0, 106.0, "OPEN_TP2"
        )
        self.assertEqual(result["status"], "SL_HIT")

    def test_short_tp1_moves_stop_to_entry(self):
        result = self.tracker._check(
            "SHORT", 97.5, 100.0, 102.0, 98.0, 96.0, 94.0, "OPEN"
        )
        self.assertEqual(result, {"status": "OPEN_TP1", "sl": 100.0})

    def test_short_tp2_keeps_signal_active(self):
        result = self.tracker._check(
            "SHORT", 95.5, 100.0, 100.0, 98.0, 96.0, 94.0, "OPEN_TP1"
        )
        self.assertEqual(result["status"], "OPEN_TP2")

    def test_short_tp3_is_terminal(self):
        result = self.tracker._check(
            "SHORT", 93.5, 100.0, 100.0, 98.0, 96.0, 94.0, "OPEN_TP2"
        )
        self.assertEqual(result["status"], "TP3_HIT")

    def test_short_direct_jump_to_tp3(self):
        result = self.tracker._check(
            "SHORT", 92.0, 100.0, 102.0, 98.0, 96.0, 94.0, "OPEN"
        )
        self.assertEqual(result["status"], "TP3_HIT")

    def test_short_direct_jump_to_tp2(self):
        result = self.tracker._check(
            "SHORT", 95.0, 100.0, 102.0, 98.0, 96.0, 94.0, "OPEN"
        )
        self.assertEqual(result, {"status": "OPEN_TP2", "sl": 100.0})

    def test_long_intrabar_tp1_detected_when_close_is_below_target(self):
        result = self.tracker._check(
            "LONG", 103.0, 100.0, 98.0, 105.0, 108.0, 112.0, "OPEN",
            high=106.0, low=101.0,
        )
        self.assertEqual(result, {"status": "OPEN_TP1", "sl": 100.0, "event_price": 105.0})

    def test_short_intrabar_tp1_detected_when_close_is_above_target(self):
        result = self.tracker._check(
            "SHORT", 97.0, 100.0, 102.0, 95.0, 92.0, 89.0, "OPEN",
            high=99.0, low=94.0,
        )
        self.assertEqual(result, {"status": "OPEN_TP1", "sl": 100.0, "event_price": 95.0})

    def test_long_intrabar_sl_detected_when_close_is_above_stop(self):
        result = self.tracker._check(
            "LONG", 103.0, 100.0, 98.0, 105.0, 108.0, 112.0, "OPEN",
            high=104.0, low=97.0,
        )
        self.assertEqual(result, {"status": "SL_HIT", "event_price": 98.0})

    def test_short_intrabar_sl_detected_when_close_is_below_stop(self):
        result = self.tracker._check(
            "SHORT", 97.0, 100.0, 102.0, 95.0, 92.0, 89.0, "OPEN",
            high=103.0, low=96.0,
        )
        self.assertEqual(result, {"status": "SL_HIT", "event_price": 102.0})

    def test_intrabar_tp3_uses_target_as_event_price(self):
        result = self.tracker._check(
            "LONG", 103.0, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN_TP2",
            high=107.0, low=101.0,
        )
        self.assertEqual(result, {"status": "TP3_HIT", "event_price": 106.0})

    def test_sl_remains_conservative_when_candle_spans_stop_and_target(self):
        result = self.tracker._check(
            "LONG", 103.0, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN",
            high=107.0, low=97.0,
        )
        self.assertEqual(result, {"status": "SL_HIT", "event_price": 98.0})

    def test_invalid_direction_is_ignored(self):
        result = self.tracker._check(
            "SIDEWAYS", 103.0, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN",
            high=107.0, low=97.0,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
