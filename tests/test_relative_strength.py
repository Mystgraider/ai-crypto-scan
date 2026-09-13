import math

from engines.relative_strength import RelativeStrengthEngine


def _series(start: float, end: float, periods: int = 20) -> list[float]:
    step = (end - start) / periods
    return [start + step * i for i in range(periods + 1)]


def _neutral(result: dict) -> None:
    assert result == {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}


def test_bear_btc_bull_coin_is_strong():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 105.0),
        _series(100.0, 90.0),
    )

    assert result["coin_ret"] == 5.0
    assert result["btc_ret"] == -10.0
    assert result["rs_ratio"] > 1.0
    assert result["rs_score"] >= 70
    assert result["rs_label"] == "STRONG"


def test_bear_btc_less_bearish_coin_outperforms():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 95.0),
        _series(100.0, 90.0),
    )

    assert result["rs_ratio"] > 1.0
    assert result["rs_label"] == "NEUTRAL"


def test_bull_btc_bull_coin_underperforming_is_below_parity():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 105.0),
        _series(100.0, 110.0),
    )

    assert result["rs_ratio"] < 1.0
    assert result["rs_score"] < 60


def test_bull_btc_bear_coin_is_weak():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 90.0),
        _series(100.0, 110.0),
    )

    assert result["rs_ratio"] < 1.0
    assert result["rs_label"] == "WEAK"


def test_equal_performance_is_parity():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 110.0),
        _series(200.0, 220.0),
    )

    assert result["rs_ratio"] == 1.0
    assert result["rs_score"] == 60.0
    assert result["rs_label"] == "NEUTRAL"


def test_insufficient_data_returns_neutral():
    result = RelativeStrengthEngine().calculate([100.0] * 10, [100.0] * 10)
    _neutral(result)


def test_invalid_start_price_returns_neutral():
    result = RelativeStrengthEngine().calculate(
        _series(0.0, 100.0),
        _series(100.0, 110.0),
    )
    _neutral(result)


def test_nan_start_or_end_returns_neutral():
    engine = RelativeStrengthEngine()
    cases = [
        ([math.nan] + [100.0] * 20, [100.0] * 21),
        (_series(100.0, math.nan), [100.0] * 21),
        ([100.0] * 21, [math.nan] + [100.0] * 20),
        ([100.0] * 21, _series(100.0, math.nan)),
    ]
    for coin, btc in cases:
        _neutral(engine.calculate(coin, btc))


def test_infinite_start_or_end_returns_neutral():
    engine = RelativeStrengthEngine()
    cases = [
        ([math.inf] + [100.0] * 20, [100.0] * 21),
        ([100.0] * 20 + [math.inf], [100.0] * 21),
        ([100.0] * 21, [math.inf] + [100.0] * 20),
        ([100.0] * 21, [100.0] * 20 + [math.inf]),
    ]
    for coin, btc in cases:
        _neutral(engine.calculate(coin, btc))


def test_zero_or_negative_end_price_returns_neutral():
    engine = RelativeStrengthEngine()
    for end in (0.0, -1.0):
        _neutral(engine.calculate(_series(100.0, end), [100.0] * 21))
        _neutral(engine.calculate([100.0] * 21, _series(100.0, end)))


def test_near_total_loss_is_finite_and_neutral_when_input_is_valid():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 0.01),
        _series(100.0, 0.01),
    )
    assert math.isfinite(result["rs_ratio"])
    assert result["rs_ratio"] == 1.0
    assert result["rs_label"] == "NEUTRAL"


def test_zero_returns_are_parity():
    result = RelativeStrengthEngine().calculate([100.0] * 21, [200.0] * 21)
    assert result["rs_ratio"] == 1.0
    assert result["rs_score"] == 60.0
    assert result["rs_label"] == "NEUTRAL"


def test_exact_strong_boundary():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 100.0 * (70.0 / 60.0)),
        [100.0] * 21,
    )
    assert result["rs_score"] == 70.0
    assert result["rs_label"] == "STRONG"


def test_exact_weak_boundary_below_neutral():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 100.0 * (49.99 / 60.0)),
        [100.0] * 21,
    )
    assert result["rs_score"] < 50.0
    assert result["rs_label"] == "WEAK"
