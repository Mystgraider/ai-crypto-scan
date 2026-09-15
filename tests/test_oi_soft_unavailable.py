from engines.oi_engine import OIEngine


class FailingOIExchange:
    def fetch_open_interest(self, symbol):
        raise RuntimeError("OI unavailable")


def test_oi_fetch_failure_is_soft_evidence():
    result = OIEngine().fetch_oi(FailingOIExchange(), "ETH/USDT:USDT")

    assert result["available"] is True
    assert result["data_available"] is False
    assert result["reason"] == "fetch_error"


def test_oi_unavailable_never_adds_score():
    result = OIEngine()._unavailable("test")

    assert result["available"] is True
    assert result["data_available"] is False
    assert result["oi_signal"] == "UNAVAILABLE"
    assert result["score_adj"] == 0
