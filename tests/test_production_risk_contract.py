from pathlib import Path

from config import CONFIG
from engines.direction_policy import get_candidate_directions


ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scanner_v5.py"
LIVE_ENTRY = ROOT / "engines" / "live_entry_integrity.py"
RRCE_ENGINE = ROOT / "engines" / "rrce_engine.py"
TP_LADDER = ROOT / "engines" / "tp_ladder.py"


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


def _source(path):
    return path.read_text(encoding="utf-8")


def test_direction_discovery_is_independent():
    for trend_direction in ("NONE", "LONG", "SHORT"):
        assert get_candidate_directions(trend_direction, False) == ["LONG", "SHORT"]


def test_no_legacy_global_direction_gates_remain():
    scanner = _source(SCANNER)
    assert "pause_shorts" not in scanner
    assert "block_bear_regime" not in scanner
    assert "range_regime_min_score" not in scanner

    assert "pause_shorts" not in CONFIG
    assert "block_bear_regime" not in CONFIG
    assert "range_regime_min_score" not in CONFIG


def test_btc_normal_regimes_remain_context_only():
    source = _source(ROOT / "engines" / "btc_filter.py")
    # Normal BULL/BEAR/RANGE states must not globally choose a coin direction.
    assert 'return self._r("BULL"' in source
    assert 'allow_long=True, allow_short=True' in source
    assert 'return self._r("BEAR"' in source
    assert 'return self._r("RANGE"' in source

    # Only explicit safety states may block directions.
    assert 'allow_long=False, allow_short=False' in source


def test_rrce_is_the_only_production_sl_tp_authority():
    scanner = _source(SCANNER)
    live_entry = _source(LIVE_ENTRY)
    rrce = _source(RRCE_ENGINE)
    ladder = _source(TP_LADDER)

    assert not (ROOT / "engines" / "risk_engine.py").exists()
    assert "RiskEngine" not in scanner
    assert "live_entry_levels(" not in scanner
    assert "revalidate_live_entry(" in scanner
    assert "build_tp_ladder(" in live_entry
    assert 'stage4=stage4' in live_entry
    assert 'result = rrce_engine.live_entry_levels(' in live_entry
    assert 'entry=result["entry"]' in live_entry
    assert 'structural_tp=result["tp3"]' in live_entry
    assert "structural_tp=result[\"tp3\"]" in live_entry

    # RRCE owns the structural entry/SL/TP contract; the ladder owns TP1/TP2/TP3.
    assert 'planned_entry = float(stage4["entry"])' in rrce
    assert 'sl = float(stage4["sl"])' in rrce
    assert 'tp = float(stage4["tp"])' in rrce
    assert 'def build_tp_ladder(' in ladder
    assert 'tp3 = structural_tp' in ladder

    # Scanner candidates must consume the already validated risk object.
    assert '"entry":           risk["entry"]' in scanner
    assert '"sl":              risk["sl"]' in scanner
    assert '"tp1":             risk["tp1"]' in scanner
    assert '"tp2":             risk["tp2"]' in scanner
    assert '"tp3":             risk["tp3"]' in scanner

    assert LEGACY_RISK_CONFIG_KEYS.isdisjoint(CONFIG)
    for key in LEGACY_RISK_CONFIG_KEYS:
        assert key not in scanner
        assert key not in rrce


def test_final_candidate_pipeline_stays_direction_first_and_rank_second():
    scanner = _source(SCANNER)

    directions_pos = scanner.index("for direction in candidate_directions:")
    risk_pos = scanner.index("rrce_risk = revalidate_live_entry(", directions_pos)
    validator_pos = scanner.index("if not validator.validate(", risk_pos)
    candidate_pos = scanner.index("candidates.append({", validator_pos)

    assert directions_pos < risk_pos < validator_pos < candidate_pos

    # Composite/ranking data must be calculated after structural validation,
    # not used as a pre-validation direction gate.
    composite_pos = scanner.index("composite =", candidate_pos - 1000)
    assert validator_pos < composite_pos < candidate_pos


def test_rrce_live_contract_remains_configured():
    assert CONFIG["min_rr"] >= 2.0
    assert CONFIG["rrce_entry_max_deviation_pct"] > 0


def test_production_contract_does_not_silently_restore_old_defaults():
    scanner = _source(SCANNER)
    # A missing config key must never silently re-enable a legacy hard gate.
    assert 'CONFIG.get("pause_shorts"' not in scanner
    assert 'CONFIG.get("block_bear_regime"' not in scanner
    assert 'CONFIG.get("range_regime_min_score"' not in scanner


def test_rrce_live_entry_fails_closed_on_unvalidated_stage4():
    from engines.rrce_engine import RRCEEngine

    result = RRCEEngine.live_entry_levels(
        direction="LONG",
        live_price=100.0,
        stage4={"valid": False, "entry": 99.0, "sl": 95.0, "tp": 110.0},
        max_deviation_pct=1.0,
        min_rr=2.0,
    )

    assert result == {"valid": False, "reason": "invalid_stage4"}



def test_beta_unavailable_does_not_fabricate_neutral_one():
    scanner = _source(SCANNER)
    assert '"beta_label": "N/A", "beta": 1.0' not in scanner
    assert '"beta_label": "UNAVAILABLE", "beta": None' in scanner


def test_rrce_evaluate_accepts_and_forwards_confirmation_window():
    import inspect

    from engines.rrce_engine import RRCEEngine

    signature = inspect.signature(RRCEEngine.evaluate)
    params = signature.parameters

    assert params["direction"].annotation is str
    assert params["patience_bars"].default == 6
    assert params["confirmation_bars"].default == 3

    rrce = _source(RRCE_ENGINE)
    assert "confirmation_bars=confirmation_bars" in rrce
    assert 'CONFIG["rrce_stage3_confirmation_bars"]' in _source(SCANNER)
