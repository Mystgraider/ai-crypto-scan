import unittest
import sys
import types

# These tests cover the pure live-entry validation helper.  Keep them runnable
# in minimal environments where the data-frame dependencies have not yet been
# installed; the helper itself does not use either library.
try:
    import pandas  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pandas"] = types.SimpleNamespace(DataFrame=object)

try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    sys.modules["numpy"] = types.SimpleNamespace()

from engines.rrce_engine import RRCEEngine


class LiveEntryLevelsTests(unittest.TestCase):
    def test_long_uses_executable_price_with_structural_levels(self):
        result = RRCEEngine.live_entry_levels(
            direction="LONG",
            live_price=100.3,
            stage4={"entry": 100.0, "sl": 98.0, "tp": 106.0},
            max_deviation_pct=0.4,
            min_rr=2.0,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["entry"], 100.3)
        self.assertEqual(result["sl"], 98.0)
        self.assertEqual(result["tp1"], 106.0)
        self.assertGreaterEqual(result["rr"], 2.0)

    def test_rejects_price_that_has_moved_beyond_entry_tolerance(self):
        result = RRCEEngine.live_entry_levels(
            direction="LONG",
            live_price=100.5,
            stage4={"entry": 100.0, "sl": 98.0, "tp": 106.0},
            max_deviation_pct=0.4,
            min_rr=2.0,
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "price_away_from_rrce_entry")

    def test_short_uses_structural_stop_and_target(self):
        result = RRCEEngine.live_entry_levels(
            direction="SHORT",
            live_price=99.8,
            stage4={"entry": 100.0, "sl": 102.0, "tp": 94.0},
            max_deviation_pct=0.4,
            min_rr=2.0,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["sl"], 102.0)
        self.assertEqual(result["tp1"], 94.0)


if __name__ == "__main__":
    unittest.main()
