from engines.circuit_breaker import _count_canonical_losses


TODAY = "2026-09-13"


def _signal(**overrides):
    signal = {
        "timestamp": f"{TODAY}T04:00:00Z",
        "status": "SL_HIT",
        "direction": "LONG",
        "entry": 100.0,
        "exit_price": 98.0,
        "initial_sl": 102.0,
        "realized_r": -1.0,
    }
    signal.update(overrides)
    return signal


def test_counts_negative_canonical_realized_r_as_loss():
    signals = [_signal()]
    assert _count_canonical_losses(signals, TODAY) == 1


def test_does_not_count_positive_r_sl_hit_as_loss():
    signals = [
        _signal(
            realized_r=1.0,
            tp1_qty_pct=50,
            tp1_exit_price=104,
            tp1_realized_r=2.0,
            tp1_executed_at="2026-09-13T01:00:00Z",
            remaining_position_pct=50,
            remaining_position_exit_r=0.0,
        )
    ]
    assert _count_canonical_losses(signals, TODAY) == 0


def test_does_not_count_zero_r_sl_hit_as_loss():
    signals = [_signal(realized_r=0.0)]
    assert _count_canonical_losses(signals, TODAY) == 0


def test_excludes_unresolved_terminal_signal():
    signals = [
        _signal(
            realized_r="",
            exit_price="",
            initial_sl=98.0,
        )
    ]
    assert _count_canonical_losses(signals, TODAY) == 0


def test_excludes_non_terminal_negative_realized_r():
    signals = [_signal(status="OPEN", realized_r=-1.0)]
    assert _count_canonical_losses(signals, TODAY) == 0


def test_excludes_other_dates():
    signals = [_signal(timestamp="2026-09-12T23:59:00Z")]
    assert _count_canonical_losses(signals, TODAY) == 0
