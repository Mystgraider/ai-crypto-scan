from pathlib import Path

import pandas as pd
import pytest

from tools import historical_replay as hr

ROOT = Path(__file__).resolve().parents[1]
REPLAY_SRC = (ROOT / "tools" / "historical_replay.py").read_text()


def test_default_keeps_long_disabled(monkeypatch):
    monkeypatch.delenv("BACKTEST_ALLOW_LONG", raising=False)
    assert hr.allow_long_research() is False
    assert hr.replay_direction_policy(hr.allow_long_research()) == ["SHORT"]


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", "2"])
def test_non_opt_in_values_keep_long_disabled(monkeypatch, value):
    monkeypatch.setenv("BACKTEST_ALLOW_LONG", value)
    assert hr.allow_long_research() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes "])
def test_explicit_opt_in_enables_long(monkeypatch, value):
    monkeypatch.setenv("BACKTEST_ALLOW_LONG", value)
    assert hr.allow_long_research() is True
    assert hr.replay_direction_policy(True) == ["LONG", "SHORT"]


def test_replay_sets_flag_and_metadata_from_the_switch_only():
    assert '"true" if allow_long else "false"' in REPLAY_SRC
    assert '"long_signals_enabled": allow_long' in REPLAY_SRC
    assert "replay_direction_policy(allow_long)" in REPLAY_SRC
    # no unconditional enable remains
    assert 'os.environ["LONG_SIGNALS_ENABLED"] = "true"\n' not in REPLAY_SRC


def _long():
    return {"direction": "LONG", "entry": 100.0, "sl": 95.0, "tp1": 102.0,
            "tp2": 104.0, "tp3": 106.0, "_replay_time": "2026-10-01T12:00:00+00:00"}


def _future(high, low, n=72 * 12):
    ts = pd.date_range(start=_long()["_replay_time"], periods=n, freq="5min")
    return pd.DataFrame({"timestamp": ts, "high": [high] * n, "low": [low] * n})


def test_long_same_candle_sl_and_tp3_resolves_sl_first():
    candles = _future(high=101.0, low=99.0)
    candles.loc[0, "high"] = 107.0   # touches TP3
    candles.loc[0, "low"] = 94.0     # and SL in the same candle
    assert hr.historical_outcome(_long(), candles)["status"] == "SL_HIT"


def test_long_tp3_without_sl_is_tp3():
    candles = _future(high=101.0, low=99.0)
    candles.loc[3, "high"] = 107.0
    assert hr.historical_outcome(_long(), candles)["status"] == "TP3_HIT"


def test_long_no_touch_full_window_is_expired():
    assert hr.historical_outcome(_long(), _future(101.0, 99.0))["status"] == "EXPIRED"
