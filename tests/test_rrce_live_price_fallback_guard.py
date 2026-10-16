import unittest
from unittest.mock import Mock

from scanner_v5 import _ensure_risk_fallback, _rrce_live_risk_invalid


class RrceLiveRiskFallbackTests(unittest.TestCase):
    def test_ticker_failure_does_not_mark_none_as_invalid_rrce_result(self):
        self.assertFalse(_rrce_live_risk_invalid(None))

    def test_ticker_failure_uses_atr_risk_fallback(self):
        engine = Mock()
        expected = {"sl": 98.0, "tp1": 104.0, "tp2": 108.0, "tp3": 112.0}
        engine.calculate.return_value = expected
        actual = _ensure_risk_fallback(None, engine, "LONG", 100.0, 2.0)
        self.assertIs(actual, expected)
        engine.calculate.assert_called_once_with("LONG", 100.0, 2.0)

    def test_valid_rrce_risk_does_not_call_atr_fallback(self):
        engine = Mock()
        rrce_risk = {"valid": True, "entry": 100.0}
        actual = _ensure_risk_fallback(rrce_risk, engine, "LONG", 100.0, 2.0)
        self.assertIs(actual, rrce_risk)
        engine.calculate.assert_not_called()

    def test_explicit_invalid_rrce_result_is_rejected(self):
        self.assertTrue(_rrce_live_risk_invalid({"valid": False, "reason": "bad_entry"}))


if __name__ == "__main__":
    unittest.main()
