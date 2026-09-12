from engines.tp_ladder import build_tp_ladder
import pytest


@pytest.mark.parametrize("rr", [2.0, 2.5, 3.0, 4.0])
def test_long_ladder_is_ordered_and_structural_tp_is_final(rr):
    entry = 100.0
    risk = 2.0
    structural_tp = entry + rr * risk
    result = build_tp_ladder("LONG", entry, structural_tp)
    assert result["entry"] < result["tp1"] < result["tp2"] <= result["tp3"]
    assert result["tp3"] == structural_tp


@pytest.mark.parametrize("rr", [2.0, 2.5, 3.0, 4.0])
def test_short_ladder_is_ordered_and_structural_tp_is_final(rr):
    entry = 100.0
    risk = 2.0
    structural_tp = entry - rr * risk
    result = build_tp_ladder("SHORT", entry, structural_tp)
    assert result["entry"] > result["tp1"] > result["tp2"] >= result["tp3"]
    assert result["tp3"] == structural_tp


@pytest.mark.parametrize(
    "direction,entry,target",
    [("LONG", 100.0, 100.0), ("LONG", 100.0, 99.0),
     ("SHORT", 100.0, 100.0), ("SHORT", 100.0, 101.0)],
)
def test_rejects_non_profitable_structural_target(direction, entry, target):
    with pytest.raises(ValueError, match="profit direction"):
        build_tp_ladder(direction, entry, target)


def test_rejects_invalid_direction():
    with pytest.raises(ValueError, match="LONG or SHORT"):
        build_tp_ladder("SIDEWAYS", 100.0, 110.0)


def test_rejects_invalid_fractions():
    with pytest.raises(ValueError, match="fractions"):
        build_tp_ladder("LONG", 100.0, 110.0, tp1_fraction=0.75, tp2_fraction=0.50)
