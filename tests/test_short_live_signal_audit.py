import numpy as np
import pandas as pd
import pytest

from tools import short_live_signal_audit as audit


def _write_signals(tmp_path, rows):
    path = tmp_path / "signals.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def _rows(n_days=12, per_day=20, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(per_day):
            bear_caution = (i % 4 == 0)
            # planted effect: BEAR_CAUTION rarely hits TP3, everything else often does
            hit = rng.random() < (0.10 if bear_caution else 0.50)
            entry = 100.0
            rows.append({
                "timestamp": f"2026-10-{d + 1:02d}T{i % 24:02d}:{i:02d}:00+00:00",
                "symbol": f"S{i}/USDT:USDT", "direction": "SHORT",
                "entry": entry, "initial_sl": 102.0, "tp3": 92.0,
                "adx": 15.0 if i % 2 else 30.0, "rsi": 55.0 if i % 3 else 40.0,
                "btc_regime": "BEAR_CAUTION" if bear_caution else "RANGE",
                "status": "TP3_HIT" if hit else "SL_HIT",
                "realized_r": 4.0 if hit else -1.0,
            })
    # LONG rows must be ignored entirely
    rows.append({**rows[0], "direction": "LONG", "status": "TP3_HIT"})
    return rows


def test_long_rows_are_ignored(tmp_path):
    path = _write_signals(tmp_path, _rows())
    df = audit.load_short(path, "2026-10-01")
    assert set(df["status"]).issubset(set(audit.KNOWN))
    assert len(df) == 12 * 20  # the single LONG row is excluded


def test_start_filter_excludes_earlier_rows(tmp_path):
    path = _write_signals(tmp_path, _rows())
    df = audit.load_short(path, "2026-10-07")
    assert df["ts"].min() >= pd.Timestamp("2026-10-07", tz="UTC")


def test_thirds_are_chronological_and_non_overlapping(tmp_path):
    df = audit.assign_thirds(audit.load_short(_write_signals(tmp_path, _rows()), "2026-10-01"))
    res = df[df["resolved"]]
    spans = res.groupby("seg")["ts"].agg(["min", "max"])
    assert spans.loc["discovery", "max"] <= spans.loc["development", "min"]
    assert spans.loc["development", "max"] <= spans.loc["holdout", "min"]


def test_sl_distance_is_computed_from_initial_sl_not_trailing_sl(tmp_path):
    rows = _rows()
    for r in rows:
        r["sl"] = 99.0  # trailing SL below entry must not leak into planned distance
    df = audit.load_short(_write_signals(tmp_path, rows), "2026-10-01")
    assert df["sl_dist_pct"].round(6).eq(2.0).all()


def test_planted_bear_caution_effect_is_detected(tmp_path):
    result = audit.run(_write_signals(tmp_path, _rows()), "2026-10-01", boots=300, seed=5)
    base = result["configs"]["A_baseline"]["tp3_rate"]
    kept = result["configs"]["C_rsi_not_bear_caution"]["tp3_rate"]
    assert kept > base
    assert result["configs"]["C_rsi_not_bear_caution"]["vs_baseline_day_clustered"]["ci95_pp"][0] > 0


def test_gate_configs_are_pure_filters_and_do_not_change_sl_geometry(tmp_path):
    df = audit.assign_thirds(audit.load_short(_write_signals(tmp_path, _rows()), "2026-10-01"))
    before = df[["entry", "initial_sl", "sl_dist_pct"]].copy()
    for mask in audit.configs(df).values():
        assert mask.index.equals(df.index) and mask.dtype == bool
    pd.testing.assert_frame_equal(before, df[["entry", "initial_sl", "sl_dist_pct"]])


def test_too_few_resolved_trades_fails_loudly(tmp_path):
    rows = _rows(n_days=1, per_day=1)
    df = audit.load_short(_write_signals(tmp_path, rows), "2026-10-01")
    with pytest.raises(ValueError):
        audit.assign_thirds(df)
