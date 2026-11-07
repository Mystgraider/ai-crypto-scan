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
        start=start,
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
    assert result["expected_candles"] == 864
    assert result["observed_candles"] == 864


def test_missing_candle_is_incomplete_not_expired():
    candles = _future_5m().drop(index=100).reset_index(drop=True)
    result = historical_outcome(_signal(), candles)
    assert result["status"] == "INCOMPLETE_DATA"
    assert result["missing_candles"] == 1
    assert result["expected_candles"] == 864


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


def test_first_candle_opening_at_signal_time_is_scored():
    candles = _future_5m()
    candles.loc[0, "high"] = 106.0
    result = historical_outcome(_signal(), candles)
    assert result["status"] == "SL_HIT"
    assert result["event_time"] == _signal()["_replay_time"]


def test_same_first_candle_sl_and_tp3_uses_conservative_sl_first():
    candles = _future_5m()
    candles.loc[0, "high"] = 106.0
    candles.loc[0, "low"] = 93.0
    result = historical_outcome(_signal(), candles)
    assert result["status"] == "SL_HIT"
    assert result["event_time"] == _signal()["_replay_time"]


def _replay_store(end):
    end = pd.Timestamp(end)
    five_min_times = pd.date_range(
        end - pd.Timedelta(minutes=60),
        end,
        freq="5min",
    )
    five_min = pd.DataFrame({
        "timestamp": five_min_times,
        "open": [100.0 + i for i in range(len(five_min_times))],
        "high": [101.0 + i for i in range(len(five_min_times))],
        "low": [99.0 + i for i in range(len(five_min_times))],
        "close": [100.5 + i for i in range(len(five_min_times))],
        "volume": [10.0] * len(five_min_times),
    })
    hourly = pd.DataFrame({
        "timestamp": pd.date_range(
            end - pd.Timedelta(hours=3), end - pd.Timedelta(hours=1), freq="1h"
        ),
        "open": [90.0, 91.0, 92.0],
        "high": [91.0, 92.0, 93.0],
        "low": [89.0, 90.0, 91.0],
        "close": [90.5, 91.5, 92.5],
        "volume": [100.0] * 3,
    })
    four_hour = pd.DataFrame({
        "timestamp": [end.floor("4h") - pd.Timedelta(hours=4)],
        "open": [80.0], "high": [85.0], "low": [79.0],
        "close": [84.0], "volume": [400.0],
    })
    fifteen = pd.DataFrame({
        "timestamp": [end.floor("15min") - pd.Timedelta(minutes=15)],
        "open": [95.0], "high": [96.0], "low": [94.0],
        "close": [95.5], "volume": [50.0],
    })
    return HistoricalStore(
        candles={
            ("TEST/USDT:USDT", "5m"): five_min,
            ("TEST/USDT:USDT", "1h"): hourly,
            ("TEST/USDT:USDT", "4h"): four_hour,
            ("TEST/USDT:USDT", "15m"): fifteen,
        },
        funding={}, oi={}, end=end,
    )


def test_replay_exposes_forming_1h_candle_and_completed_previous_bar():
    from tools.historical_replay import ReplayMarketLoader

    store = _replay_store("2026-10-01T02:00:00Z")
    frame = ReplayMarketLoader(store).get_1h("TEST/USDT:USDT")
    assert frame.iloc[-1]["timestamp"] == store.end
    assert frame.iloc[-1]["open"] == pytest.approx(112.0)
    assert frame.iloc[-1]["close"] == pytest.approx(112.0)
    assert frame.iloc[-2]["timestamp"] == store.end - pd.Timedelta(hours=1)


def test_replay_forming_4h_uses_only_closed_5m_bars_and_boundary_open():
    from tools.historical_replay import ReplayMarketLoader

    store = _replay_store("2026-10-01T02:00:00Z")
    frame = ReplayMarketLoader(store).get_4h("TEST/USDT:USDT")
    forming = frame.iloc[-1]
    assert forming["timestamp"] == pd.Timestamp("2026-10-01T00:00:00Z")
    assert forming["close"] == pytest.approx(112.0)
    assert forming["high"] == pytest.approx(112.0)
    assert forming["low"] == pytest.approx(99.0)
    assert forming["volume"] == pytest.approx(120.0)


def test_replay_boundary_ticker_uses_next_candle_open_not_previous_close():
    from tools.historical_replay import ReplayExchange

    store = _replay_store("2026-10-01T02:00:00Z")
    assert ReplayExchange(store).fetch_ticker("TEST/USDT:USDT")["last"] == pytest.approx(112.0)


def test_replay_fails_closed_without_boundary_price():
    from tools.historical_replay import ReplayExchange

    store = _replay_store("2026-10-01T02:00:00Z")
    store.candles[("TEST/USDT:USDT", "5m")] = store.candles[
        ("TEST/USDT:USDT", "5m")
    ].iloc[:-1]
    with pytest.raises(RuntimeError, match="missing_5m_boundary_price"):
        ReplayExchange(store).fetch_ticker("TEST/USDT:USDT")
