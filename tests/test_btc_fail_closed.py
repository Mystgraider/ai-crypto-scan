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


def _btc_frame(ema20, ema50, price, adx=30, rsi=55):
    import pandas as pd

    return pd.DataFrame([
        {"close": price, "ema_20": ema20, "ema_50": ema50, "adx": adx, "rsi": rsi},
        {"close": price, "ema_20": ema20, "ema_50": ema50, "adx": adx, "rsi": rsi},
    ])


def test_normal_btc_bull_keeps_both_directions_available():
    result = BTCFilter().analyze(_btc_frame(ema20=101, ema50=99, price=102, rsi=60))

    assert result["regime"] == "BULL"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_normal_btc_bear_keeps_both_directions_available():
    result = BTCFilter().analyze(_btc_frame(ema20=99, ema50=101, price=98, rsi=50))

    assert result["regime"] == "BEAR_UNCONFIRMED"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_btc_range_keeps_both_directions_available():
    result = BTCFilter().analyze(_btc_frame(ema20=100, ema50=100, price=100, rsi=55))

    assert result["regime"] == "RANGE"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_btc_extreme_oversold_blocks_both_directions():
    result = BTCFilter().analyze(_btc_frame(ema20=99, ema50=101, price=98, rsi=25))

    assert result["allow_long"] is False
    assert result["allow_short"] is False


def test_btc_extreme_overbought_only_blocks_long():
    result = BTCFilter().analyze(_btc_frame(ema20=101, ema50=99, price=102, rsi=80))

    assert result["allow_long"] is False
    assert result["allow_short"] is True
