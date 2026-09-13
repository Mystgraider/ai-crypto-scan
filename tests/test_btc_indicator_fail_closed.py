import pandas as pd
import pytest

from indicators.indicators import Indicators


def _btc_frame():
    df = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1.0],
        }
    )
    df.attrs["btc_market_data"] = True
    return df


def test_btc_indicator_processing_error_returns_unavailable(monkeypatch):
    def _boom(_df):
        raise RuntimeError("synthetic BTC indicator failure")

    monkeypatch.setattr(Indicators, "_apply", staticmethod(_boom))

    result = Indicators.apply(_btc_frame())

    assert result.attrs["btc_market_data"] is True
    assert result.attrs["btc_data_unavailable"] is True


def test_non_btc_indicator_processing_error_still_raises(monkeypatch):
    def _boom(_df):
        raise RuntimeError("synthetic non-BTC indicator failure")

    monkeypatch.setattr(Indicators, "_apply", staticmethod(_boom))

    df = _btc_frame()
    df.attrs.pop("btc_market_data")

    with pytest.raises(RuntimeError, match="synthetic non-BTC indicator failure"):
        Indicators.apply(df)
