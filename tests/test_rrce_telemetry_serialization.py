from pathlib import Path
import csv

import scanner_v5
from storage import signal_logger


def test_scanner_forwards_rrce_stage_telemetry_to_save_signal():
    source = Path("scanner_v5.py").read_text(encoding="utf-8")
    required = [
        'rrce_stage1_passed=sig.get("rrce_stage1_passed")',
        'rrce_stage2_passed=sig.get("rrce_stage2_passed")',
        'rrce_stage3_passed=sig.get("rrce_stage3_passed")',
        'rrce_stage4_valid=sig.get("rrce_stage4_valid")',
        'rrce_stage4_entry_zone=sig.get("rrce_stage4_entry_zone")',
    ]
    for fragment in required:
        assert fragment in source


def test_signal_logger_persists_rrce_stage_telemetry(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="ETH/USDT:USDT",
        direction="SHORT",
        entry=100.0,
        sl=102.0,
        tp1=99.0,
        tp2=98.0,
        tp3=96.0,
        rr=2.0,
        rrce_stage1_passed=True,
        rrce_stage1_position_pct=72.5,
        rrce_stage1_zone="PREMIUM",
        rrce_stage1_range_width_pct=8.25,
        rrce_stage2_passed=True,
        rrce_stage2_pool_level=101.0,
        rrce_stage2_sweep_extreme=102.5,
        rrce_stage2_sweep_time="2026-11-10T10:00:00+00:00",
        rrce_stage3_passed=True,
        rrce_stage3_choch_level=100.5,
        rrce_stage3_break_time="2026-11-10T10:15:00+00:00",
        rrce_stage3_fvg_top=100.8,
        rrce_stage3_fvg_bottom=100.4,
        rrce_stage4_valid=True,
        rrce_stage4_entry_zone="OB",
        rrce_stage4_rr=3.25,
        rrce_stage4_ob_top=100.6,
        rrce_stage4_ob_bottom=99.8,
        rrce_stage4_fvg_top=100.2,
        rrce_stage4_fvg_bottom=99.9,
    )

    with path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))

    assert row["rrce_stage1_passed"] == "true"
    assert float(row["rrce_stage1_position_pct"]) == 72.5
    assert row["rrce_stage1_zone"] == "PREMIUM"
    assert row["rrce_stage2_passed"] == "true"
    assert row["rrce_stage2_sweep_extreme"] == "102.5"
    assert row["rrce_stage3_passed"] == "true"
    assert row["rrce_stage3_break_time"] == "2026-11-10T10:15:00+00:00"
    assert row["rrce_stage4_valid"] == "true"
    assert row["rrce_stage4_entry_zone"] == "OB"
    assert float(row["rrce_stage4_rr"]) == 3.25
