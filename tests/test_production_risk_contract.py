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


def test_rrce_is_optional_and_only_authority_when_structurally_valid():
    scanner = _source(SCANNER)
    live_entry = _source(LIVE_ENTRY)
    rrce = _source(RRCE_ENGINE)
    ladder = _source(TP_LADDER)
    fallback_risk = _source(ROOT / "engines" / "risk_engine.py")

    assert "RiskEngine" in scanner
    assert "risk_engine.calculate(" in scanner
    assert "legacy_v672_engine.evaluate(" in scanner
    assert "revalidate_live_entry(" in scanner
    assert 'if sig.get("_rrce_stage4"):' in scanner
    assert "live_entry_levels(" not in scanner
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

    directions_pos = scanner.index("for direction in allowed_directions:")
    risk_pos = scanner.index("rrce_risk = revalidate_live_entry(", directions_pos)
    validator_pos = scanner.index("if not validator.validate(", risk_pos)
    candidate_pos = scanner.index("candidates.append({", validator_pos)

    assert directions_pos < risk_pos < validator_pos < candidate_pos

    # Composite/ranking data must be calculated after structural validation,
    # not used as a pre-validation direction gate.
    composite_pos = scanner.index("composite =", validator_pos)
    assert validator_pos < composite_pos < candidate_pos


def test_rrce_live_contract_remains_configured():
    assert CONFIG["min_rr"] >= 2.0
    assert CONFIG["rrce_entry_max_deviation_pct"] > 0

def test_rrce_fallback_candidates_do_not_carry_stale_stage4_marker():
    scanner = _source(SCANNER)

    # A candidate may fall back to ATR risk when RRCE is nonqualifying or
    # when RRCE live revalidation fails. Such a candidate must not be marked
    # for a second RRCE live revalidation after ranking.
    assert '"_rrce_stage4":   rrce_execution_stage4' in scanner
    assert 'if rrce_execution_stage4 is not None else None' in scanner
    assert 'rrce_execution_stage4 = None' in scanner


def test_production_contract_does_not_silently_restore_old_defaults():
    scanner = _source(SCANNER)
    # A missing config key must never silently re-enable a legacy hard gate.
    assert 'CONFIG.get("pause_shorts"' not in scanner
    assert 'CONFIG.get("block_bear_regime"' not in scanner
    assert 'CONFIG.get("range_regime_min_score"' not in scanner


def test_rrce_stage4_revalidation_uses_exchange_ticker_price():
    scanner = _source(SCANNER)
    # Stage-4 deviation must use the exchange ticker, not the 1h forming
    # candle close. Final live validation already uses the same ticker source.
    rrce_block = scanner.index('if rrce_result and rrce_result.get("valid"):')
    revalidate_pos = scanner.index('revalidate_live_entry(', rrce_block)
    ticker_pos = scanner.index('exchange.fetch_ticker(symbol)["last"]', rrce_block)
    assert ticker_pos < revalidate_pos
    assert 'live_price=rrce_live_price' in scanner[rrce_block:scanner.index('else:', revalidate_pos) + 5]


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


def test_stage23_diagnostic_replay_guards_missing_stage1():
    scanner = _source(SCANNER)
    guard = 'if not isinstance(_s1v, dict):'
    stage2_call = '_diag_engine.stage2_retail_liquidity('
    range_access = '_s1v["range_low"], _s1v["range_high"]'

    call_index = scanner.index(stage2_call)
    guard_index = scanner.index(guard, max(0, call_index - 1200), call_index)
    block = scanner[guard_index:call_index]
    assert guard in block
    assert range_access not in scanner[guard_index - 200:guard_index]


def test_stage1_variant_stage4_replay_aligns_15m_break_to_5m_timestamp():
    scanner = _source(SCANNER)

    # Stage-4 diagnostics consume the 5m execution dataframe, so a 15m
    # positional break index must never be passed directly into that frame.
    assert "_s3_break_idx = _s3v.get(\"break_idx\")" in scanner
    assert "_confirm_ts = pd.to_datetime(" in scanner
    assert "_exec_ts = pd.to_datetime(" in scanner
    assert "_matches = [i for i, _ts in enumerate(_exec_ts) if _ts == _confirm_ts]" in scanner
    assert "break_idx=_s4_break_idx" in scanner
    assert "break_idx=_s3v.get(\"break_idx\")" not in scanner

    alignment_pos = scanner.index("_matches = [i for i, _ts in enumerate(_exec_ts) if _ts == _confirm_ts]")
    stage4_pos = scanner.index("break_idx=_s4_break_idx", alignment_pos)
    assert alignment_pos < stage4_pos


def test_candidate_fate_telemetry_covers_ranking_and_live_rejections():
    scanner = _source(SCANNER)

    # Every candidate must remain traceable after CANDIDATE_FOUND through
    # ranking, live validation, and final signal delivery/rejection.
    assert 'def _record_fate(sym, direction, fate, **extra):' in scanner
    assert '"CANDIDATE_FOUND"' in scanner
    assert '"RANKED"' in scanner
    assert '"LIVE_PRICE_DRIFT_REJECT"' in scanner
    assert '"LIVE_RRCE_REVALIDATION_REJECT"' in scanner
    assert '"LIVE_VALIDATION_ERROR"' in scanner
    assert '"LIVE_VALIDATED"' in scanner
    assert '"SIGNAL_SENT"' in scanner
    assert '"candidate_fate_counts": dict(fate_counts)' in scanner
    assert '"candidate_fate_counts_pre_ranking": dict(fate_counts)' in scanner
    assert '"candidate_fate_trace_event_count": len(symbol_trace_log)' in scanner
    assert '"skip_counts": dict(skip)' in scanner


def test_candidate_fate_telemetry_records_all_candidates_not_only_trace_symbols():
    scanner = _source(SCANNER)

    # The legacy symbol trace is intentionally filtered for expensive
    # diagnostics, but candidate fate events must be forced into telemetry
    # so downstream candidate loss cannot disappear silently.
    assert '_record_fate(' in scanner
    assert 'force=True' in scanner
    assert 'skip["candidate_found"] += 1' in scanner


def test_high_composite_scores_are_not_rejected_by_artificial_ceiling():
    scanner = _source(SCANNER)
    config = _source(ROOT / "config.py")
    assert '"signal_score_s": 95' in config
    assert '"signal_score_ceiling"' not in config
    assert 'CONFIG.get("signal_score_ceiling", 84)' not in scanner
    assert 'composite >= CONFIG.get("signal_score_ceiling", 84)' not in scanner
    assert 'if g == "D":' in scanner


def test_rrce_classification_is_persisted_with_every_signal():
    scanner = _source(SCANNER)
    logger = _source(ROOT / "storage" / "signal_logger.py")
    for field in (
        "rrce_status",
        "rrce_failed_stage",
        "rrce_failure_reason",
        "rrce_choch_confirmed",
        "rrce_risk_contract",
        "rrce_engine_mode",
    ):
        assert field in logger
        assert f'{field}=sig.get("{field}"' in scanner


def test_rrce_fallback_metadata_is_not_labeled_qualified():
    scanner = _source(SCANNER)
    assert '_rrce_risk_contract = "RRCE" if rrce_execution_stage4 is not None else "ATR_FALLBACK"' in scanner
    assert '_rrce_status = "QUALIFIED" if rrce_execution_stage4 is not None' in scanner
    assert '"rrce_risk_contract": _rrce_risk_contract' in scanner
    assert '"rrce_status": _rrce_status' in scanner

def test_rrce_stage4_fate_telemetry_is_complete():
    scanner = _source(SCANNER)
    assert '"RRCE_STAGE4_VALID"' in scanner
    assert '"RRCE_STAGE4_LIVE_REJECT"' in scanner
    assert '"RRCE_STAGE4_LIVE_PASS"' in scanner
    assert '"RRCE_STAGE4_POST_LIVE_BLOCK"' in scanner
