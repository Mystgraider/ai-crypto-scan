import json
from pathlib import Path

from tools.short_quality_score import derive_weights, score_rows


def make_row(i, outcome, range_width, adx4h, macd15, macd1h, roc, atr, support, rsi):
    return {
        "direction": "SHORT",
        "outcome": outcome,
        "replay_time": f"2026-01-{(i % 28) + 1:02d}T00:00:00",
        "rrce_stage1_range_width_pct": range_width,
        "adx_4h": adx4h,
        "macd_hist_15m": macd15,
        "macd_hist": macd1h,
        "roc": roc,
        "atr_pct": atr,
        "support_distance_pct": support,
        "rsi": rsi,
        "entry": 100.0,
        "sl": 101.0,
    }


def test_weights_are_derived_from_discovery_data_only():
    discovery = []
    for i in range(20):
        discovery.append(make_row(i, "TP3_HIT", 10 + i, 10, 0.1, 0.1, 2, 0.5, 3, 60))
        discovery.append(make_row(i + 40, "SL_HIT", 5, 30 + i, -0.1, -0.1, -2, 1.5, 0.2, 45))
    weights, medians, _ = derive_weights([discovery])
    assert weights
    assert medians["range_width_4h"] > 0.5
    assert medians["adx_4h"] < 0.5
    assert sum(abs(v) for v in weights.values()) > 0


def test_score_requires_complete_feature_set():
    discovery = []
    for i in range(10):
        discovery.append(make_row(i, "TP3_HIT", 10, 10, 0.1, 0.1, 2, 0.5, 3, 60))
        discovery.append(make_row(i + 20, "SL_HIT", 5, 30, -0.1, -0.1, -2, 1.5, 0.2, 45))
    weights, _, _ = derive_weights([discovery])
    rows = [
        make_row(100, "TP3_HIT", 12, 9, 0.2, 0.2, 3, 0.4, 4, 65),
        {**make_row(101, "TP3_HIT", 12, 9, 0.2, 0.2, 3, 0.4, 4, 65), "roc": None},
    ]
    scored = score_rows(rows, weights, discovery)
    assert len(scored) == 1
    assert "research_short_quality_score" in scored[0]
