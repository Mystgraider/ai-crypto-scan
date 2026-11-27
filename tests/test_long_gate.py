import pandas as pd

from engines.long_gate import evaluate_long_setup


def _frame(rows):
    return pd.DataFrame(rows)


def _base():
    h1 = _frame([
        {"close": 100, "ema_20": 99, "ema_50": 97, "atr": 2, "rsi": 55, "macd_hist": -0.2},
        {"close": 98, "ema_20": 99, "ema_50": 97, "atr": 2, "rsi": 52, "macd_hist": 0.1},
        {"close": 101, "ema_20": 100, "ema_50": 97, "atr": 2, "rsi": 58, "macd_hist": 0.4},
        {"close": 101.2, "ema_20": 100.2, "ema_50": 97.2, "atr": 2, "rsi": 58, "macd_hist": 0.45},
    ])
    h4 = _frame([
        {"close": 99, "ema_20": 98, "ema_50": 96, "rsi": 60},
        {"close": 101, "ema_20": 99, "ema_50": 97, "rsi": 62},
        {"close": 101.5, "ema_20": 99.5, "ema_50": 97.5, "rsi": 63},
    ])
    m15 = _frame([
        {"close": 99, "ema_20": 100, "ema_50": 98, "macd_hist": -0.1},
        {"close": 98.5, "ema_20": 99.5, "ema_50": 98, "macd_hist": 0.0},
        {"close": 100.5, "ema_20": 100, "ema_50": 98.5, "macd_hist": 0.2},
        {"close": 101, "ema_20": 100.2, "ema_50": 98.7, "macd_hist": 0.25},
    ])
    return h1, h4, m15


def test_long_pullback_reclaim_passes():
    h1, h4, m15 = _base()
    result = evaluate_long_setup(h1, h4, m15, 101.0)
    assert result["valid"] is True
    assert result["setup"] == "LONG_PULLBACK_RECLAIM"


def test_long_rejects_overextended_rsi():
    h1, h4, m15 = _base()
    h1.loc[h1.index[-2], "rsi"] = 72
    result = evaluate_long_setup(h1, h4, m15, 101.0)
    assert result["valid"] is False
    assert result["reason"] == "long_setup_conditions_not_met"


def test_long_requires_bullish_15m_confirmation():
    h1, h4, m15 = _base()
    m15.loc[m15.index[-2], "ema_20"] = 101.0
    m15.loc[m15.index[-2], "ema_50"] = 102.0
    m15.loc[m15.index[-2], "close"] = 99.0
    m15.loc[m15.index[-2], "macd_hist"] = -0.3
    result = evaluate_long_setup(h1, h4, m15, 101.0)
    assert result["valid"] is False


def test_long_rejects_chase():
    h1, h4, m15 = _base()
    result = evaluate_long_setup(h1, h4, m15, 104.0)
    assert result["valid"] is False
