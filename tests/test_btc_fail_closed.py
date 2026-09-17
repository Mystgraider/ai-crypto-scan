"""Regression coverage for the production BTC fail-closed path."""

from config import CONFIG
from engines.btc_filter import BTCFilter
from indicators.indicators import Indicators
from loaders.market_data_loader import MarketDataLoader


class _FailingExchange:
    def fetch_ohlcv(self, symbol, timeframe, limit):
        raise RuntimeError("BTC data unavailable")


def test_btc_1h_fetch_failure_becomes_blocked_unknown_state():
    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = _FailingExchange()

    raw = loader.get_1h(CONFIG["btc_symbol"])
    assert raw.attrs["btc_data_unavailable"] is True
    assert len(raw) == 1

    prepared = Indicators.apply(raw)
    result = BTCFilter().analyze(prepared)

    assert result["regime"] == "UNKNOWN"
    assert result["allow_long"] is False
    assert result["allow_short"] is False
    assert "no signals" in result["reason"]


def test_non_btc_fetch_failure_still_raises():
    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = _FailingExchange()

    try:
        loader.get_1h("ETH/USDT:USDT")
    except RuntimeError as exc:
        assert "BTC data unavailable" in str(exc)
    else:
        raise AssertionError("non-BTC fetch failures must not be swallowed")
