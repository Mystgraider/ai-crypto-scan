import unittest

from scanner_v5 import _rrce_live_risk_invalid


class RrceLiveRiskGuardTests(unittest.TestCase):
    def test_none_means_ticker_unavailable_and_fallback_not_invalid_result(self):
        self.assertFalse(_rrce_live_risk_invalid(None))

    def test_explicit_invalid_result_is_rejected(self):
        self.assertTrue(_rrce_live_risk_invalid({"valid": False, "reason": "bad_entry"}))

    def test_valid_result_is_not_rejected(self):
        self.assertFalse(_rrce_live_risk_invalid({"valid": True, "entry": 100.0}))


if __name__ == "__main__":
    unittest.main()
