from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engines import short_gate as g

ROOT = Path(__file__).resolve().parents[1]
SCANNER = (ROOT / "scanner_v5.py").read_text()
CONFIG_SRC = (ROOT / "config.py").read_text()


def _df(closed_rsi, forming_rsi=99.0, n=5):
    rsi = [60.0] * (n - 2) + [closed_rsi, forming_rsi]
    return pd.DataFrame({"rsi": rsi})


def test_allows_at_or_above_floor_and_rejects_below():
    assert g.short_rsi_4h_check(_df(50.0), 50.0) == (True, None, 50.0)
    assert g.short_rsi_4h_check(_df(62.3), 50.0)[0] is True
    allowed, reason, value = g.short_rsi_4h_check(_df(49.99), 50.0)
    assert (allowed, reason) == (False, g.REASON_FLOOR) and value == pytest.approx(49.99)


def test_reads_last_closed_candle_never_the_forming_one():
    # forming candle (iloc[-1]) says 99 but the closed candle is 40 -> must reject
    assert g.short_rsi_4h_check(_df(40.0, forming_rsi=99.0), 50.0)[1] == g.REASON_FLOOR
    # forming candle says 10 but the closed candle is 60 -> must allow
    assert g.short_rsi_4h_check(_df(60.0, forming_rsi=10.0), 50.0)[0] is True


def test_no_lookahead_changing_forming_candle_cannot_change_decision():
    base = g.short_rsi_4h_check(_df(55.0, forming_rsi=1.0), 50.0)
    for forming in (1.0, 50.0, 99.0, float("nan")):
        assert g.short_rsi_4h_check(_df(55.0, forming_rsi=forming), 50.0) == base


@pytest.mark.parametrize("frame", [
    None,
    pd.DataFrame({"rsi": [55.0]}),                       # fewer than 2 candles
    pd.DataFrame({"close": [1.0, 2.0, 3.0]}),             # no rsi column
    pd.DataFrame({"rsi": [55.0, np.nan, 60.0]}),          # closed candle NaN
    pd.DataFrame({"rsi": [55.0, None, 60.0]}),
])
def test_missing_4h_rsi_fails_closed_with_explicit_reason(frame):
    assert g.short_rsi_4h_check(frame, 50.0) == (False, g.REASON_UNAVAILABLE, None)


def test_disabled_gate_never_blocks_even_with_missing_data():
    for floor in (0.0, None):
        assert g.short_rsi_4h_check(None, floor) == (True, None, None)


@pytest.mark.parametrize("bad", [-1.0, 100.0, 120.0, float("nan"), float("inf"), "abc"])
def test_config_validation_rejects_unusable_floor(bad):
    with pytest.raises(ValueError):
        g.validate_short_gate_config({"short_rsi_4h_floor": bad})


def test_config_validation_floor_must_be_below_ceiling():
    with pytest.raises(ValueError):
        g.validate_short_gate_config({"short_rsi_4h_floor": 70.0, "short_rsi_ceiling": 70.0})
    g.validate_short_gate_config({"short_rsi_4h_floor": 50.0, "short_rsi_ceiling": 70.0})


def test_shipped_config_is_valid_and_set_to_validated_floor():
    from config import CONFIG
    g.validate_short_gate_config(CONFIG)
    assert CONFIG["short_rsi_4h_floor"] == 50.0
    assert CONFIG["short_rsi_floor"] == 50.0 and CONFIG["short_rsi_ceiling"] == 70.0


def _short_block():
    start = SCANNER.index('if direction == "SHORT":')
    end = SCANNER.index("quality_score = quality_engine.score(", start)
    return SCANNER[start:end]


def test_gate_is_wired_inside_short_block_only_with_explicit_skip_reason():
    block = _short_block()
    assert "short_rsi_4h_check(" in block
    assert "df_4h" in block and "skip[short_rsi_4h_reason]" in block
    assert SCANNER.count("short_rsi_4h_check(") == 1  # not reachable from any other path
    assert 'direction == "LONG"' not in block


def test_gate_does_not_touch_risk_or_sl_tp_geometry():
    block = _short_block()
    for forbidden in ("risk_engine.calculate(", "revalidate_live_entry(", 'risk["sl"]',
                      'risk["tp3"]', "position_sizer", "leverage"):
        assert forbidden not in block


def test_long_path_and_removed_hard_gates_unchanged():
    for key in ("short_adx_max", "short_atr_max_pct", "short_price_to_ema20_band"):
        assert key not in CONFIG_SRC
        assert key not in _short_block()
    helper = (ROOT / "engines" / "short_gate.py").read_text()
    assert "LONG" not in helper.split('"""', 2)[2]  # helper code has no LONG logic
