from engines.oi_engine import OIEngine


class _CurrentOnlyExchange:
    def fetch_open_interest(self, symbol):
        return {"openInterestValue": 1000}

    def fetch_open_interest_history(self, symbol, timeframe, limit):
        raise RuntimeError("history endpoint unavailable")


class _CompleteExchange:
    def fetch_open_interest(self, symbol):
        return {"openInterestValue": 1100}

    def fetch_open_interest_history(self, symbol, timeframe, limit):
        return [
            {"openInterestValue": 1000},
            {"openInterestValue": 1100},
        ]


def test_oi_history_failure_is_soft_and_explicitly_unavailable():
    result = OIEngine().fetch_oi(_CurrentOnlyExchange(), "ETH/USDT:USDT")

    assert result["available"] is True
    assert result["data_available"] is False
    assert result["reason"] == "oi_history_fetch_error"

    analyzed = OIEngine().analyze(
        current_oi=result["current_oi"],
        previous_oi=result["previous_oi"],
        price_change=1.0,
        direction="LONG",
    )
    assert analyzed["oi_signal"] == "UNAVAILABLE"
    assert analyzed["score_adj"] == 0


def test_complete_oi_data_remains_directional_evidence():
    result = OIEngine().fetch_oi(_CompleteExchange(), "ETH/USDT:USDT")

    assert result["available"] is True
    assert result["data_available"] is True

    analyzed = OIEngine().analyze(
        current_oi=result["current_oi"],
        previous_oi=result["previous_oi"],
        price_change=1.0,
        direction="LONG",
    )
    assert analyzed["oi_signal"] == "CONFIRMED"
    assert analyzed["score_adj"] == 10
