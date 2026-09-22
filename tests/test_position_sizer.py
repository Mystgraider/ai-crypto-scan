import pytest

from engines.position_sizer import PositionSizer


def test_valid_sizing_remains_unchanged():
    result = PositionSizer().calculate("A", 75, 100.0, 98.0, 1000.0)
    assert result["risk_pct"] == 1.5
    assert result["risk_usdt"] == 15.0
    assert result["position_usdt"] == 750.0
    assert result["leverage"] == 4


@pytest.mark.parametrize("grade", ["", "D", None])
def test_rejects_invalid_grade(grade):
    with pytest.raises(ValueError, match="invalid_grade"):
        PositionSizer().calculate(grade, 75, 100.0, 98.0, 1000.0)


@pytest.mark.parametrize("confidence", [-1, 101, float("nan"), float("inf"), float("-inf")])
def test_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        PositionSizer().calculate("A", confidence, 100.0, 98.0, 1000.0)


@pytest.mark.parametrize("entry,sl", [(0, 98.0), (-1, 98.0), (100.0, 0), (100.0, -1), (float("nan"), 98.0), (100.0, float("inf"))])
def test_rejects_invalid_price_inputs(entry, sl):
    with pytest.raises(ValueError):
        PositionSizer().calculate("A", 75, entry, sl, 1000.0)


@pytest.mark.parametrize("account", [0, -1, float("nan"), float("inf")])
def test_rejects_invalid_account(account):
    with pytest.raises(ValueError, match="invalid_account"):
        PositionSizer().calculate("A", 75, 100.0, 98.0, account)
