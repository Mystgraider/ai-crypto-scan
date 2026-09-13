from engines.relative_strength import RelativeStrengthEngine


def _series(start: float, end: float, periods: int = 20) -> list[float]:
    step = (end - start) / periods
    return [start + step * i for i in range(periods + 1)]


def test_bear_btc_bull_coin_is_strong():
    result = RelativeStrengthEngine().calculate(
        _series(100.0, 105.0),
        _series(100.0, 90.0),
    )

    assert result["coin_ret"] == 5.0
    assert result["btc_ret"] == -10.0
    assert result["rs_ratio"] > 1.0
    assert result["rs_score"] > 70
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
    result = RelativeStrengthEngine().calculate(
        [100.0] * 10,
        [100.0] * 10,
    )

    assert result == {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}


def test_invalid_start_price_returns_neutral():
    result = RelativeStrengthEngine().calculate(
        _series(0.0, 100.0),
        _series(100.0, 110.0),
    )

    assert result["rs_score"] == 50.0
    assert result["rs_label"] == "NEUTRAL"
