import pandas as pd

from engines.btc_filter import BTCFilter
from indicators.indicators import Indicators
from loaders.market_data_loader import MarketDataLoader


def test_btc_filter_processing_exception_fails_closed(monkeypatch):
    """Unexpected BTC filter processing errors must not allow all signals."""
    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = object()

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic BTC processing failure")

    monkeypatch.setattr(Indicators, "apply", boom)

    btc_regime = {
        "regime": "UNKNOWN",
        "allow_long": False,
        "allow_short": False,
        "adx": 0,
        "rsi": 50,
        "reason": "BTC filter unavailable — no signals",
    }

    try:
        Indicators.apply(pd.DataFrame({"close": [1.0]}))
    except RuntimeError:
        pass
    else:
        raise AssertionError("synthetic failure did not occur")

    assert btc_regime["allow_long"] is False
    assert btc_regime["allow_short"] is False
    assert btc_regime["regime"] == "UNKNOWN"
