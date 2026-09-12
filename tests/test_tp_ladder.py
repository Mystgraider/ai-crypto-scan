import pytest

from engines.tp_ladder import build_tp_ladder


@pytest.mark.parametrize("rr", [2.0, 2.5, 3.0, 4.0])
def test_long_ladder_is_ordered_and_structural_tp_is_final(rr):
    entry = 100.0
    risk = 2.0
    structural_tp = entry + rr * risk
    result = build_tp_ladder("LONG", entry, structural_tp)

    assert result["entry"] < result["tp1"] < result["tp2"] < result["tp3"]
    assert result["tp3"] == structural_tp
    assert result["tp1"] == entry + (structural_tp - entry) * 0.50
    assert result["tp2"] == entry + (structural_tp - entry) * 0.75


@pytest.mark.parametrize("rr", [2.0, 2.5, 3.0, 4.0])
def test_short_ladder_is_ordered_and_structural_tp_is_final(rr):
    entry = 100.0
    risk = 2.0
    structural_tp = entry - rr * risk
    result = build_tp_ladder("SHORT", entry, structural_tp)

    assert result["entry"] > result["tp1"] > result["tp2"] > result["tp3"]
    assert result["tp3"] == structural_tp
    assert result["tp1"] == entry - (entry - structural_tp) * 0.50
    assert result["tp2"] == entry - (entry - structural_tp) * 0.75


@pytest.mark.parametrize(
    "direction,entry,target",
    [
        ("LONG", 100.0, 100.0),
        ("LONG", 100.0, 99.0),
        ("SHORT", 100.0, 100.0),
        ("SHORT", 100.0, 101.0),
    ],
)
def test_rejects_non_profitable_structural_target(direction, entry, target):
    with pytest.raises(ValueError, match="profit direction"):
        build_tp_ladder(direction, entry, target)


def test_rejects_invalid_direction():
    with pytest.raises(ValueError, match="LONG or SHORT"):
        build_tp_ladder("SIDEWAYS", 100.0, 110.0)


@pytest.mark.parametrize(
    "tp1_fraction,tp2_fraction",
    [(0.75, 0.50), (0.0, 0.50), (0.50, 1.01)],
)
def test_rejects_invalid_fractions(tp1_fraction, tp2_fraction):
    with pytest.raises(ValueError, match="fractions"):
        build_tp_ladder(
            "LONG",
            100.0,
            110.0,
            tp1_fraction=tp1_fraction,
            tp2_fraction=tp2_fraction,
        )


def test_supports_custom_ladder_fractions():
    result = build_tp_ladder(
        "LONG", 100.0, 108.0, tp1_fraction=0.25, tp2_fraction=0.50
    )

    assert result["tp1"] == 102.0
    assert result["tp2"] == 104.0
    assert result["tp3"] == 108.0
    assert result["tp1_fraction"] == 0.25
    assert result["tp2_fraction"] == 0.50


def test_rejects_non_positive_prices():
    with pytest.raises(ValueError, match="positive"):
        build_tp_ladder("LONG", 0.0, 10.0)


def test_does_not_modify_structural_target():
    structural_tp = 108.0
    result = build_tp_ladder("LONG", 100.0, structural_tp)

    assert result["structural_tp"] == structural_tp
    assert result["tp3"] == structural_tp
