import pandas as pd
import pytest

from tools.historical_replay import (
    historical_outcome,
    validate_hourly_timeline,
)
from indicators.indicators import Indicators


def _signal():
    return {
        "direction": "SHORT",
        "entry": 100.0,
        "sl": 105.0,
        "tp1": 98.0,
        "tp2": 96.0,
        "tp3": 94.0,
        "_replay_time": "2026-10-01T12:00:00+00:00",
    }


def _future_5m():
    start = pd.Timestamp(_signal()["_replay_time"])
    timestamps = pd.date_range(
        start=start + pd.Timedelta(minutes=5),
        periods=72 * 12,
        freq="5min",
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "high": [101.0] * len(timestamps),
        "low": [99.0] * len(timestamps),
    })


def test_full_contiguous_72h_without_hit_is_expired():
    result = historical_outcome(_signal(), _future_5m())
    assert result["status"] == "EXPIRED"
    assert result["expected_candles"] == 863
    assert result["observed_candles"] == 863


def test_missing_candle_is_incomplete_not_expired():
    candles = _future_5m().drop(index=100).reset_index(drop=True)
    result = historical_outcome(_signal(), candles)
    assert result["status"] == "INCOMPLETE_DATA"
    assert result["missing_candles"] == 1
    assert result["expected_candles"] == 863


def test_terminal_hit_before_later_gap_remains_valid():
    candles = _future_5m().drop(index=100).reset_index(drop=True)
    candles.loc[0, "low"] = 93.0
    result = historical_outcome(_signal(), candles)
    assert result["status"] == "TP3_HIT"


def test_hourly_timeline_requires_every_expected_close():
    start = pd.Timestamp("2026-10-01T00:00:00Z")
    end = start + pd.Timedelta(hours=3)
    complete = pd.DataFrame({
        "timestamp": pd.date_range(
            start=start - pd.Timedelta(hours=1), periods=4, freq="1h"
        )
    })
    report = validate_hourly_timeline(complete, start, end)
    assert report["expected_hours"] == 4
    assert report["observed_hours"] == 4
    assert report["missing_hours"] == 0


def test_hourly_timeline_fails_closed_on_gap():
    start = pd.Timestamp("2026-10-01T00:00:00Z")
    end = start + pd.Timedelta(hours=3)
    incomplete = pd.DataFrame({
        "timestamp": [
            start - pd.Timedelta(hours=1),
            start + pd.Timedelta(hours=1),
            start + pd.Timedelta(hours=2),
        ]
    })
    with pytest.raises(RuntimeError, match="incomplete_hourly_replay_timeline"):
        validate_hourly_timeline(incomplete, start, end)



def test_directional_movement_tie_does_not_create_false_minus_di():
    frame = pd.DataFrame({
        "close": [100.0] * 65,
        "high": [101.0] * 65,
        "low": [99.0] * 65,
        "volume": [1000.0] * 65,
    })
    # Equal +DM and -DM on this candle must cancel to zero by Wilder's
    # directional-movement definition; it must not be counted as -DM.
    frame.loc[30, "high"] = 103.0
    frame.loc[30, "low"] = 97.0

    result = Indicators.apply(frame)
    assert "plus_di_research" in result.columns
    assert "minus_di_research" in result.columns
    assert result.loc[30, "plus_di_research"] == pytest.approx(0.0)
    assert result.loc[30, "minus_di_research"] == pytest.approx(0.0)


def test_directional_indicators_identify_downward_pressure():
    close = [120.0 - index * 0.5 for index in range(65)]
    frame = pd.DataFrame({
        "close": close,
        "high": [value + 0.25 for value in close],
        "low": [value - 0.75 for value in close],
        "volume": [1000.0] * len(close),
    })

    result = Indicators.apply(frame)
    assert result.loc[64, "minus_di_research"] > result.loc[64, "plus_di_research"]
    assert result.loc[64, "adx"] > 0
