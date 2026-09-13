from engines.live_entry_integrity import revalidate


class FakeRRCE:
    def live_entry_levels(self, direction, live_price, stage4, max_deviation_pct, min_rr):
        planned = stage4["entry"]
        sl = stage4["sl"]
        tp = stage4["tp"]
        if abs(live_price - planned) / planned * 100 > max_deviation_pct:
            return {"valid": False, "reason": "price_away_from_rrce_entry"}
        risk = abs(live_price - sl)
        reward = abs(tp - live_price)
        rr = reward / risk if risk else 0.0
        if rr < min_rr:
            return {"valid": False, "reason": "rr_below_minimum"}
        return {
            "valid": True,
            "entry": live_price,
            "sl": sl,
            "tp1": tp,
            "tp2": tp,
            "tp3": tp,
            "rr": rr,
        }


def test_revalidate_recalculates_rr_from_fresh_price_and_builds_tp_ladder():
    result = revalidate(
        FakeRRCE(),
        "LONG",
        105.0,
        {"entry": 100.0, "sl": 95.0, "tp": 115.0},
        max_deviation_pct=10.0,
        min_rr=1.0,
    )

    assert result["valid"] is True
    assert result["entry"] == 105.0
    assert result["sl"] == 95.0
    assert result["tp1"] == 110.0
    assert result["tp2"] == 112.5
    assert result["tp3"] == 115.0
    assert result["structural_tp"] == 115.0
    assert result["tp1_fraction"] == 0.50
    assert result["tp2_fraction"] == 0.75
    assert result["rr"] == 1.0


def test_revalidate_builds_short_tp_ladder():
    result = revalidate(
        FakeRRCE(),
        "SHORT",
        95.0,
        {"entry": 100.0, "sl": 105.0, "tp": 85.0},
        max_deviation_pct=10.0,
        min_rr=1.0,
    )

    assert result["valid"] is True
    assert result["entry"] == 95.0
    assert result["sl"] == 105.0
    assert result["tp1"] == 90.0
    assert result["tp2"] == 87.5
    assert result["tp3"] == 85.0
    assert result["structural_tp"] == 85.0


def test_revalidate_rejects_stale_price():
    result = revalidate(
        FakeRRCE(),
        "LONG",
        112.0,
        {"entry": 100.0, "sl": 95.0, "tp": 115.0},
        max_deviation_pct=10.0,
        min_rr=1.0,
    )

    assert result["valid"] is False
    assert result["reason"] == "price_away_from_rrce_entry"
