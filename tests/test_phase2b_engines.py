import math

from engines.beta_filter import BetaFilter
from engines.funding_engine import FundingEngine
from engines.oi_engine import OIEngine


def test_beta_uses_covariance_not_volatility_ratio():
    btc = [100, 101, 102, 101, 103, 104, 106, 105, 107, 109, 110, 111, 113, 112, 114, 116, 117, 119, 118, 120, 122]
    coin = [50, 50.5, 51, 50.5, 51.5, 52, 53, 52.5, 53.5, 54.5, 55, 55.5, 56.5, 56, 57, 58, 58.5, 59.5, 59, 60, 61]
    beta = BetaFilter().calculate_beta(coin, btc, periods=20)
    assert beta is not None
    assert 0.8 < beta < 1.2


def test_beta_returns_unavailable_when_btc_variance_is_zero():
    btc = [100.0] * 21
    coin = [50 + i for i in range(21)]
    assert BetaFilter().calculate_beta(coin, btc, periods=20) is None


def test_beta_unavailable_is_soft_not_fake_neutral():
    result = BetaFilter().classify("X/USDT:USDT", None)
    assert result["beta"] is None
    assert result["beta_label"] == "UNAVAILABLE"
    assert result["short_ok"] is True
    assert result["preferred"] is False


def test_beta_high_threshold_blocks_short_but_not_long():
    engine = BetaFilter()
    result = engine.classify("X/USDT:USDT", 1.5)
    assert result["short_ok"] is False
    long_result = engine.evaluate("X/USDT:USDT", "LONG", [1, 2], [1, 2])
    assert long_result["short_ok"] is True


def test_beta_hard_gate_overrides_preferred_short_list():
    result = BetaFilter().classify("ETH/USDT:USDT", 1.6)
    assert result["short_ok"] is False
    assert result["beta_label"] == "HIGH"


def test_known_high_beta_blocks_short():
    result = BetaFilter().classify("DOGE/USDT:USDT", 0.5)
    assert result["short_ok"] is False


def test_funding_zero_is_available_but_nan_is_soft_unavailable():
    engine = FundingEngine()
    assert engine.analyze(0.0)["available"] is True
    unavailable = engine.analyze(float("nan"))
    assert unavailable["available"] is False
    assert unavailable["data_available"] is False
    assert unavailable["funding_pct"] is None
    assert unavailable["long_ok"] is True
    assert unavailable["short_ok"] is True
    assert unavailable["short_score_adj"] == 0


def test_oi_invalid_values_are_unavailable_not_neutral():
    result = OIEngine().analyze(0, 0, 0, "LONG")
    assert result["available"] is False
    assert result["oi_signal"] == "UNAVAILABLE"
    assert result["score_adj"] == 0
    assert result["oi_change_pct"] is None


def test_oi_real_observation_can_still_be_neutral():
    result = OIEngine().analyze(100, 100, 0.0, "LONG")
    assert result["available"] is True
    assert result["oi_signal"] == "NEUTRAL"
    assert result["oi_change_pct"] == 0.0
