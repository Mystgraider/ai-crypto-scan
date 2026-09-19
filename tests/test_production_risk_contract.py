from pathlib import Path

from config import CONFIG


LEGACY_RISK_CONFIG_KEYS = {
    "min_sl_pct",
    "sl_atr_mult",
    "tp1_atr_mult",
    "tp2_atr_mult",
    "tp3_atr_mult",
    "short_sl_atr_mult",
    "short_tp1_atr_mult",
    "short_tp2_atr_mult",
    "short_tp3_atr_mult",
}


def test_rrce_is_the_only_production_sl_tp_authority():
    scanner = Path("scanner_v5.py").read_text(encoding="utf-8")
    live_entry = Path("engines/live_entry_integrity.py").read_text(encoding="utf-8")

    assert not Path("engines/risk_engine.py").exists()
    assert "RiskEngine" not in scanner
    assert "live_entry_levels" in scanner
    assert "revalidate_live_entry" in scanner
    assert "build_tp_ladder" in live_entry

    assert LEGACY_RISK_CONFIG_KEYS.isdisjoint(CONFIG)


def test_rrce_live_contract_remains_configured():
    assert CONFIG["min_rr"] >= 2.0
    assert CONFIG["rrce_entry_max_deviation_pct"] > 0
