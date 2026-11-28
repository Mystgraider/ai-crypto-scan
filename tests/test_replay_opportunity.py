from datetime import timedelta

import pandas as pd

from tools.replay_opportunity import deduplicate_long_opportunities


def _signal(minutes, symbol="SOL/USDT:USDT", direction="LONG"):
    ts = pd.Timestamp("2026-10-01T00:00:00Z") + timedelta(minutes=minutes)
    return {
        "symbol": symbol,
        "direction": direction,
        "_replay_time": ts.isoformat(),
        "_replay_timestamp": ts,
    }


def test_long_duplicate_burst_keeps_first_signal():
    rows = [_signal(0), _signal(5), _signal(10), _signal(55)]
    kept, stats = deduplicate_long_opportunities(rows)

    assert len(kept) == 1
    assert kept[0]["_replay_time"] == "2026-10-01T00:00:00+00:00"
    assert stats["suppressed_duplicate_signals"] == 3


def test_long_distinct_hourly_opportunities_are_preserved():
    rows = [_signal(0), _signal(60), _signal(120)]
    kept, stats = deduplicate_long_opportunities(rows)

    assert len(kept) == 3
    assert stats["suppressed_duplicate_signals"] == 0


def test_long_dedup_is_per_symbol_and_direction():
    rows = [
        _signal(0, "SOL/USDT:USDT", "LONG"),
        _signal(5, "ETH/USDT:USDT", "LONG"),
        _signal(10, "SOL/USDT:USDT", "SHORT"),
        _signal(15, "SOL/USDT:USDT", "LONG"),
    ]
    kept, stats = deduplicate_long_opportunities(rows)

    assert len(kept) == 3
    assert stats["suppressed_duplicate_signals"] == 1
    assert [r["direction"] for r in kept] == ["LONG", "LONG", "SHORT"]
