import os
import csv
import json
import math
from datetime import datetime, timezone
from storage.outcome_fields import DEFAULT_EXECUTION_OUTCOME, EXECUTION_OUTCOME_FIELDS

SIGNALS_FILE = "storage/signals.csv"

FIELDNAMES = [
    "timestamp", "symbol", "direction",
    "entry", "initial_sl", "sl", "tp1", "tp2", "tp3",
    "score", "grade", "rr",
    "adx", "rsi", "plus_di", "minus_di", "di_spread",
    "ema20_ema50_gap_pct", "price_to_ema20_pct", "support_distance_pct",
    "macd_hist", "stoch_k", "stoch_d", "bb_pct_b", "roc", "atr_pct",
    "ema20_1h", "ema50_1h", "price_1h_signal",
    "rsi_4h", "adx_4h", "ema20_4h", "ema50_4h", "macd_hist_4h", "stoch_k_4h", "bb_pct_b_4h",
    "rsi_15m", "adx_15m", "ema20_15m", "ema50_15m", "macd_hist_15m", "stoch_k_15m", "bb_pct_b_15m",
    "mtf_4h", "mtf_15m",
    "rel_volume", "spike_tier",
    "mtf_status", "btc_regime", "rs_label",
    "funding_pct", "oi_signal", "beta_label",
    "ai_rank_score", "ai_rank_raw", "confidence", "ai_attribution",
    "rrce_status", "rrce_failed_stage", "rrce_failure_reason",
    "rrce_choch_confirmed", "rrce_risk_contract", "rrce_engine_mode",
    "rrce_stage1_passed", "rrce_stage1_position_pct", "rrce_stage1_zone",
    "rrce_stage1_range_width_pct", "rrce_stage2_passed", "rrce_stage2_pool_level",
    "rrce_stage2_sweep_extreme", "rrce_stage2_sweep_time", "rrce_stage3_passed",
    "rrce_stage3_choch_level", "rrce_stage3_break_time", "rrce_stage3_fvg_top",
    "rrce_stage3_fvg_bottom", "rrce_stage4_valid", "rrce_stage4_entry_zone",
    "rrce_stage4_rr", "rrce_stage4_ob_top", "rrce_stage4_ob_bottom",
    "rrce_stage4_fvg_top", "rrce_stage4_fvg_bottom",
    "status",
    "tp1_hit_at", "tp2_hit_at", "tp3_hit_at",
    "exit_at", "exit_price", "realized_r",
    *EXECUTION_OUTCOME_FIELDS,
]

ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}


def _ensure_file():
    os.makedirs("storage", exist_ok=True)
    if not os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        return

    # Migrate older tracked CSV schemas in-place before any append/update.
    with open(SIGNALS_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        if existing_fields == FIELDNAMES:
            return
        rows = list(reader)

    with open(SIGNALS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def save_signal(
    symbol: str, direction: str, entry: float, sl: float,
    tp1: float, tp2: float, tp3: float,
    score: float = 0.0, grade: str = "C", rr: float = 0.0,
    adx: float = 0.0, rsi: float = 0.0, rel_volume: float = 0.0,
    plus_di: float | None = None, minus_di: float | None = None,
    di_spread: float | None = None, ema20_ema50_gap_pct: float | None = None,
    price_to_ema20_pct: float | None = None, support_distance_pct: float | None = None,
    macd_hist: float | None = None, stoch_k: float | None = None, stoch_d: float | None = None,
    bb_pct_b: float | None = None, roc: float | None = None, atr_pct: float | None = None,
    ema20_1h: float | None = None, ema50_1h: float | None = None, price_1h_signal: float | None = None,
    rsi_4h: float | None = None, adx_4h: float | None = None,
    ema20_4h: float | None = None, ema50_4h: float | None = None,
    macd_hist_4h: float | None = None, stoch_k_4h: float | None = None, bb_pct_b_4h: float | None = None,
    rsi_15m: float | None = None, adx_15m: float | None = None,
    ema20_15m: float | None = None, ema50_15m: float | None = None,
    macd_hist_15m: float | None = None, stoch_k_15m: float | None = None, bb_pct_b_15m: float | None = None,
    mtf_4h: str | None = None, mtf_15m: str | None = None,
    spike_tier: str = "", mtf_status: str = "", btc_regime: str = "",
    rs_label: str = "", funding_pct: str = "0", oi_signal: str = "",
    beta_label: str = "", ai_rank_score: float | None = None,
    ai_rank_raw: float | None = None, confidence: float | None = None,
    ai_attribution: dict | None = None,
    rrce_status: str = "NOT_RUN",
    rrce_failed_stage: str = "",
    rrce_failure_reason: str = "",
    rrce_choch_confirmed: bool = False,
    rrce_risk_contract: str = "ATR_FALLBACK",
    rrce_engine_mode: str = "",
    rrce_stage1_passed: bool | None = None,
    rrce_stage1_position_pct: float | None = None,
    rrce_stage1_zone: str | None = None,
    rrce_stage1_range_width_pct: float | None = None,
    rrce_stage2_passed: bool | None = None,
    rrce_stage2_pool_level: float | None = None,
    rrce_stage2_sweep_extreme: float | None = None,
    rrce_stage2_sweep_time: str | None = None,
    rrce_stage3_passed: bool | None = None,
    rrce_stage3_choch_level: float | None = None,
    rrce_stage3_break_time: str | None = None,
    rrce_stage3_fvg_top: float | None = None,
    rrce_stage3_fvg_bottom: float | None = None,
    rrce_stage4_valid: bool | None = None,
    rrce_stage4_entry_zone: str | None = None,
    rrce_stage4_rr: float | None = None,
    rrce_stage4_ob_top: float | None = None,
    rrce_stage4_ob_bottom: float | None = None,
    rrce_stage4_fvg_top: float | None = None,
    rrce_stage4_fvg_bottom: float | None = None,
    status: str = "OPEN",
):
    _ensure_file()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "direction": direction,
        "entry": entry, "initial_sl": sl, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": round(score, 2), "grade": grade, "rr": rr,
        "adx": round(adx, 2), "rsi": round(rsi, 2),
        "plus_di": "" if plus_di is None else round(plus_di, 4),
        "minus_di": "" if minus_di is None else round(minus_di, 4),
        "di_spread": "" if di_spread is None else round(di_spread, 4),
        "ema20_ema50_gap_pct": "" if ema20_ema50_gap_pct is None else round(ema20_ema50_gap_pct, 4),
        "price_to_ema20_pct": "" if price_to_ema20_pct is None else round(price_to_ema20_pct, 4),
        "support_distance_pct": "" if support_distance_pct is None else round(support_distance_pct, 4),
        "macd_hist": "" if macd_hist is None else round(macd_hist, 8),
        "stoch_k": "" if stoch_k is None else round(stoch_k, 3),
        "stoch_d": "" if stoch_d is None else round(stoch_d, 3),
        "bb_pct_b": "" if bb_pct_b is None else round(bb_pct_b, 4),
        "roc": "" if roc is None else round(roc, 6),
        "atr_pct": "" if atr_pct is None else round(atr_pct, 6),
        "ema20_1h": "" if ema20_1h is None else round(ema20_1h, 10),
        "ema50_1h": "" if ema50_1h is None else round(ema50_1h, 10),
        "price_1h_signal": "" if price_1h_signal is None else round(price_1h_signal, 10),
        "rsi_4h": "" if rsi_4h is None else round(rsi_4h, 4),
        "adx_4h": "" if adx_4h is None else round(adx_4h, 4),
        "ema20_4h": "" if ema20_4h is None else round(ema20_4h, 10),
        "ema50_4h": "" if ema50_4h is None else round(ema50_4h, 10),
        "macd_hist_4h": "" if macd_hist_4h is None else round(macd_hist_4h, 8),
        "stoch_k_4h": "" if stoch_k_4h is None else round(stoch_k_4h, 3),
        "bb_pct_b_4h": "" if bb_pct_b_4h is None else round(bb_pct_b_4h, 4),
        "rsi_15m": "" if rsi_15m is None else round(rsi_15m, 4),
        "adx_15m": "" if adx_15m is None else round(adx_15m, 4),
        "ema20_15m": "" if ema20_15m is None else round(ema20_15m, 10),
        "ema50_15m": "" if ema50_15m is None else round(ema50_15m, 10),
        "macd_hist_15m": "" if macd_hist_15m is None else round(macd_hist_15m, 8),
        "stoch_k_15m": "" if stoch_k_15m is None else round(stoch_k_15m, 3),
        "bb_pct_b_15m": "" if bb_pct_b_15m is None else round(bb_pct_b_15m, 4),
        "mtf_4h": "" if mtf_4h is None else mtf_4h,
        "mtf_15m": "" if mtf_15m is None else mtf_15m,
        "rel_volume": round(rel_volume, 2), "spike_tier": spike_tier,
        "mtf_status": mtf_status, "btc_regime": btc_regime,
        "rs_label": rs_label, "funding_pct": funding_pct,
        "oi_signal": oi_signal, "beta_label": beta_label,
        "ai_rank_score": "" if ai_rank_score is None else round(ai_rank_score, 2),
        "ai_rank_raw": "" if ai_rank_raw is None else round(ai_rank_raw, 2),
        "confidence": "" if confidence is None else round(confidence, 2),
        "ai_attribution": "" if ai_attribution is None else json.dumps(ai_attribution, sort_keys=True, separators=(",", ":")),
        "rrce_status": rrce_status,
        "rrce_failed_stage": rrce_failed_stage,
        "rrce_failure_reason": rrce_failure_reason,
        "rrce_choch_confirmed": "true" if rrce_choch_confirmed else "false",
        "rrce_risk_contract": rrce_risk_contract,
        "rrce_engine_mode": rrce_engine_mode,
        "rrce_stage1_passed": "" if rrce_stage1_passed is None else ("true" if rrce_stage1_passed else "false"),
        "rrce_stage1_position_pct": "" if rrce_stage1_position_pct is None else round(rrce_stage1_position_pct, 6),
        "rrce_stage1_zone": "" if rrce_stage1_zone is None else rrce_stage1_zone,
        "rrce_stage1_range_width_pct": "" if rrce_stage1_range_width_pct is None else round(rrce_stage1_range_width_pct, 6),
        "rrce_stage2_passed": "" if rrce_stage2_passed is None else ("true" if rrce_stage2_passed else "false"),
        "rrce_stage2_pool_level": "" if rrce_stage2_pool_level is None else round(rrce_stage2_pool_level, 10),
        "rrce_stage2_sweep_extreme": "" if rrce_stage2_sweep_extreme is None else round(rrce_stage2_sweep_extreme, 10),
        "rrce_stage2_sweep_time": "" if rrce_stage2_sweep_time is None else rrce_stage2_sweep_time,
        "rrce_stage3_passed": "" if rrce_stage3_passed is None else ("true" if rrce_stage3_passed else "false"),
        "rrce_stage3_choch_level": "" if rrce_stage3_choch_level is None else round(rrce_stage3_choch_level, 10),
        "rrce_stage3_break_time": "" if rrce_stage3_break_time is None else rrce_stage3_break_time,
        "rrce_stage3_fvg_top": "" if rrce_stage3_fvg_top is None else round(rrce_stage3_fvg_top, 10),
        "rrce_stage3_fvg_bottom": "" if rrce_stage3_fvg_bottom is None else round(rrce_stage3_fvg_bottom, 10),
        "rrce_stage4_valid": "" if rrce_stage4_valid is None else ("true" if rrce_stage4_valid else "false"),
        "rrce_stage4_entry_zone": "" if rrce_stage4_entry_zone is None else rrce_stage4_entry_zone,
        "rrce_stage4_rr": "" if rrce_stage4_rr is None else round(rrce_stage4_rr, 6),
        "rrce_stage4_ob_top": "" if rrce_stage4_ob_top is None else round(rrce_stage4_ob_top, 10),
        "rrce_stage4_ob_bottom": "" if rrce_stage4_ob_bottom is None else round(rrce_stage4_ob_bottom, 10),
        "rrce_stage4_fvg_top": "" if rrce_stage4_fvg_top is None else round(rrce_stage4_fvg_top, 10),
        "rrce_stage4_fvg_bottom": "" if rrce_stage4_fvg_bottom is None else round(rrce_stage4_fvg_bottom, 10),
        "status": status,
        "tp1_hit_at": "", "tp2_hit_at": "", "tp3_hit_at": "",
        "exit_at": "", "exit_price": "", "realized_r": "",
        **DEFAULT_EXECUTION_OUTCOME,
    }
    with open(SIGNALS_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)
    print(f"📝 Logged: {symbol} {direction} @ {entry}")


def load_signals() -> list[dict]:
    _ensure_file()
    with open(SIGNALS_FILE, "r", newline="") as f:
        return list(csv.DictReader(f))


def update_signal_tracking(
    symbol: str, direction: str, entry: float, new_status: str,
    new_sl: float | None = None, event_at: str | None = None,
    event_price: float | None = None, realized_r: float | None = None,
) -> bool:
    """Persist lifecycle state and event data for the latest active signal."""
    _ensure_file()
    rows = load_signals()
    updated = False
    event_at = event_at or datetime.now(timezone.utc).isoformat()

    for row in reversed(rows):
        if (
            row.get("symbol") == symbol
            and row.get("direction") == direction
            and float(row.get("entry", 0)) == entry
            and row.get("status") in ACTIVE_STATUSES
        ):
            row["status"] = new_status
            if not row.get("initial_sl"):
                row["initial_sl"] = row.get("sl", "")
            if new_sl is not None:
                row["sl"] = new_sl

            if new_status == "OPEN_TP1" and not row.get("tp1_hit_at"):
                row["tp1_hit_at"] = event_at
            elif new_status == "OPEN_TP2" and not row.get("tp2_hit_at"):
                row["tp2_hit_at"] = event_at
            elif new_status == "TP3_HIT":
                row["tp3_hit_at"] = event_at
                row["exit_at"] = event_at
            elif new_status in {"SL_HIT", "EXPIRED"}:
                row["exit_at"] = event_at

            if event_price is not None and new_status in {"TP3_HIT", "SL_HIT"}:
                row["exit_price"] = event_price
            if realized_r is not None and new_status in {"TP3_HIT", "SL_HIT", "EXPIRED"}:
                row["realized_r"] = round(realized_r, 6)

            updated = True
            break

    if updated:
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    return updated


def record_execution_event(
    symbol: str,
    direction: str,
    entry: float,
    execution_level: str,
    qty_pct: float,
    exit_price: float,
    realized_r: float,
    event_at: str | None = None,
    remaining_position_pct: float | None = None,
) -> bool:
    """Persist explicit execution evidence without changing lifecycle status.

    Execution evidence is an independent state stream from the market lifecycle.
    A TP price milestone records what the market reached; this function records
    only supplied evidence that a position was actually executed. Therefore an
    execution event remains recordable even when the lifecycle has already moved
    to TP3_HIT, SL_HIT, or EXPIRED.
    """
    if execution_level not in {"TP1", "TP2", "TP3"}:
        raise ValueError("execution_level must be TP1, TP2, or TP3")

    qty_pct = float(qty_pct)
    exit_price = float(exit_price)
    realized_r = float(realized_r)
    if not math.isfinite(qty_pct) or not 0 < qty_pct <= 100:
        raise ValueError("qty_pct must be between 0 and 100")
    if not math.isfinite(exit_price) or exit_price <= 0:
        raise ValueError("exit_price must be positive")
    if not math.isfinite(realized_r):
        raise ValueError("realized_r must be finite")
    if remaining_position_pct is not None:
        remaining_position_pct = float(remaining_position_pct)
        if not math.isfinite(remaining_position_pct) or not 0 <= remaining_position_pct <= 100:
            raise ValueError("remaining_position_pct must be between 0 and 100")

    _ensure_file()
    rows = load_signals()
    event_at = event_at or datetime.now(timezone.utc).isoformat()
    qty_field = f"{execution_level.lower()}_qty_pct"
    price_field = f"{execution_level.lower()}_exit_price"
    r_field = f"{execution_level.lower()}_realized_r"
    at_field = f"{execution_level.lower()}_executed_at"

    for row in reversed(rows):
        if (
            row.get("symbol") == symbol
            and row.get("direction") == direction
            and float(row.get("entry", 0)) == float(entry)
        ):
            if row.get(qty_field):
                return False

            executed_qty = sum(
                float(row[field]) for field in (
                    "tp1_qty_pct", "tp2_qty_pct", "tp3_qty_pct"
                ) if row.get(field)
            )
            if executed_qty + qty_pct > 100:
                raise ValueError("cumulative execution quantity cannot exceed 100%")

            row[qty_field] = round(qty_pct, 6)
            row[price_field] = round(exit_price, 10)
            row[r_field] = round(realized_r, 6)
            row[at_field] = event_at
            if remaining_position_pct is not None:
                row["remaining_position_pct"] = round(remaining_position_pct, 6)

            with open(SIGNALS_FILE, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)
            return True

    return False


def update_signal_status(symbol: str, direction: str, entry: float, new_status: str):
    """Backward-compatible wrapper for older callers."""
    return update_signal_tracking(symbol, direction, entry, new_status)
