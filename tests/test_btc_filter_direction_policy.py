import pandas as pd

from engines.btc_filter import BTCFilter


def _frame(close_values, ema20, ema50, adx, rsi):
    return pd.DataFrame(
        {
            "close": close_values,
            "ema_20": [ema20, ema20],
            "ema_50": [ema50, ema50],
            "adx": [adx, adx],
            "rsi": [rsi, rsi],
        }
    )


def _frame_4h(close_values, ema20, ema50, adx):
    return pd.DataFrame(
        {
            "close": close_values,
            "ema_20": [ema20, ema20],
            "ema_50": [ema50, ema50],
            "adx": [adx, adx],
        }
    )


def test_bull_regime_does_not_block_short():
    result = BTCFilter().analyze(
        _frame([105, 106], 104, 100, 30, 60),
    )

    assert result["regime"] == "BULL"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_bear_regime_does_not_block_long():
    result = BTCFilter().analyze(
        _frame([95, 94], 96, 100, 30, 45),
        _frame_4h([95, 94], 96, 100, 30),
    )

    assert result["regime"] == "BEAR"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_bear_caution_does_not_block_either_direction():
    result = BTCFilter().analyze(
        _frame([95, 94], 96, 100, 30, 38),
        _frame_4h([95, 94], 96, 100, 30),
    )

    assert result["regime"] == "BEAR_CAUTION"
    assert result["allow_long"] is True
    assert result["allow_short"] is True


def test_extreme_oversold_remains_hard_safety_block():
    result = BTCFilter().analyze(
        _frame([95, 94], 96, 100, 30, 24),
        _frame_4h([95, 94], 96, 100, 30),
    )

    assert result["regime"] == "EXTREME_BEAR"
    assert result["allow_long"] is False
    assert result["allow_short"] is False


def test_extreme_overbought_preserves_long_block_and_allows_short():
    result = BTCFilter().analyze(
        _frame([105, 106], 104, 100, 30, 80),
    )

    assert result["regime"] == "EXTREME_BULL"
    assert result["allow_long"] is False
    assert result["allow_short"] is True


def test_range_allows_both_directions():
    result = BTCFilter().analyze(
        _frame([100, 100.5], 100, 100, 15, 55),
    )

    assert result["regime"] == "RANGE"
    assert result["allow_long"] is True
    assert result["allow_short"] is True
