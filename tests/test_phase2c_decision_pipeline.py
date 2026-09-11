from config import CONFIG
from engines.validator import SignalValidator

def test_disabled_legacy_gates_do_not_fabricate_score():
    original_trend = CONFIG.get("require_trend_gate")
    original_quality = CONFIG.get("require_quality_engine")
    CONFIG["require_trend_gate"] = False
    CONFIG["require_quality_engine"] = False
    try:
        assert SignalValidator().validate("LONG", 10, 10, {"rr": 2.0}) is True
    finally:
        CONFIG["require_trend_gate"] = original_trend
        CONFIG["require_quality_engine"] = original_quality

def test_enabled_trend_gate_still_rejects_low_score():
    original_trend = CONFIG.get("require_trend_gate")
    original_quality = CONFIG.get("require_quality_engine")
    CONFIG["require_trend_gate"] = True
    CONFIG["require_quality_engine"] = False
    try:
        assert SignalValidator().validate("LONG", 69, 10, {"rr": 2.0}) is False
    finally:
        CONFIG["require_trend_gate"] = original_trend
        CONFIG["require_quality_engine"] = original_quality

def test_enabled_quality_gate_still_rejects_low_score():
    original_trend = CONFIG.get("require_trend_gate")
    original_quality = CONFIG.get("require_quality_engine")
    CONFIG["require_trend_gate"] = False
    CONFIG["require_quality_engine"] = True
    try:
        assert SignalValidator().validate("LONG", 10, 69, {"rr": 2.0}) is False
    finally:
        CONFIG["require_trend_gate"] = original_trend
        CONFIG["require_quality_engine"] = original_quality
