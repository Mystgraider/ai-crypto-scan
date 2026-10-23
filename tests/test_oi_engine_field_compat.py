"""Regression tests for OI field compatibility and unit consistency."""
from engines.oi_engine import OIEngine


class FakeExchange:
    def __init__(self, current, history=None, history_error=None):
        self.current = current
        self.history = history
        self.history_error = history_error

    def fetch_open_interest(self, symbol):
        return self.current

    def fetch_open_interest_history(self, symbol, timeframe="1h", limit=2):
        if self.history_error:
            raise self.history_error
        return self.history


def test_amount_field_is_supported_when_history_uses_same_field():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange(
            {"openInterestAmount": "1200"},
            [
                {"openInterestAmount": "1000"},
                {"openInterestAmount": "1200"},
            ],
        ),
        "ETH/USDT:USDT",
    )
    assert result["available"] is True
    assert result["current_oi"] == 1200.0
    assert result["previous_oi"] == 1000.0


def test_quote_value_and_contract_amount_are_never_mixed():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange(
            {"openInterestValue": "1200000"},
            [
                {"openInterestAmount": "1000"},
                {"openInterestAmount": "1200"},
            ],
        ),
        "ETH/USDT:USDT",
    )
    assert result["available"] is False
    assert result["reason"] == "previous_oi_missing_or_unit_mismatch"
    assert result["score_adj"] if "score_adj" in result else True


def test_existing_open_interest_value_path_still_works():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange(
            {"openInterestValue": 2200},
            [
                {"openInterestValue": 2000},
                {"openInterestValue": 2200},
            ],
        ),
        "ETH/USDT:USDT",
    )
    assert result["available"] is True
    assert result["current_oi"] == 2200.0
    assert result["previous_oi"] == 2000.0


def test_nested_info_field_requires_matching_history_field():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange(
            {"info": {"holdVol": "500"}},
            [
                {"info": {"holdVol": "450"}},
                {"info": {"holdVol": "500"}},
            ],
        ),
        "ETH/USDT:USDT",
    )
    assert result["available"] is True
    assert result["current_oi"] == 500.0
    assert result["previous_oi"] == 450.0


def test_unsupported_history_stays_explicitly_unavailable():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange(
            {"openInterestAmount": "1200"},
            history_error=NotImplementedError("history unsupported"),
        ),
        "ETH/USDT:USDT",
    )
    assert result["available"] is False
    assert result["reason"] == "oi_history_fetch_error"


def test_missing_current_oi_stays_unavailable():
    engine = OIEngine()
    result = engine.fetch_oi(
        FakeExchange({"info": {"unrecognizedField": "1200"}}, []),
        "ETH/USDT:USDT",
    )
    assert result["available"] is False
    assert result["reason"] == "current_oi_missing"
