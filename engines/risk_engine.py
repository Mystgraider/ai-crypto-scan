"""Risk Engine — restored fallback contract for non-RRCE-gated signals.

RRCE remains an additive confluence layer. When the modern RRCE sequence does
not produce executable levels, this engine supplies the historical ATR-based
risk levels so the scanner can continue evaluating ordinary signals.
"""

from config import CONFIG


class RiskEngine:
    def calculate(self, direction: str, entry: float, atr: float) -> dict | None:
        if direction not in ("LONG", "SHORT"):
            return None
        if not isinstance(entry, (int, float)) or entry <= 0:
            return None
        if not isinstance(atr, (int, float)) or atr <= 0:
            return None

        min_rr = float(CONFIG.get("min_rr", 2.0))
        min_sl = float(CONFIG.get("min_sl_pct", 0.003))

        if direction == "LONG":
            sl_mult = float(CONFIG.get("sl_atr_mult", 1.0))
            tp1_mult = float(CONFIG.get("tp1_atr_mult", 2.5))
            tp2_mult = float(CONFIG.get("tp2_atr_mult", 4.0))
            tp3_mult = float(CONFIG.get("tp3_atr_mult", 6.0))
            sl = round(entry - atr * sl_mult, 8)
            tp1 = round(entry + atr * tp1_mult, 8)
            tp2 = round(entry + atr * tp2_mult, 8)
            tp3 = round(entry + atr * tp3_mult, 8)
        else:
            sl_mult = float(CONFIG.get("short_sl_atr_mult", 2.0))
            tp1_mult = float(CONFIG.get("short_tp1_atr_mult", 4.5))
            tp2_mult = float(CONFIG.get("short_tp2_atr_mult", 6.0))
            tp3_mult = float(CONFIG.get("short_tp3_atr_mult", 8.0))
            sl = round(entry + atr * sl_mult, 8)
            tp1 = round(entry - atr * tp1_mult, 8)
            tp2 = round(entry - atr * tp2_mult, 8)
            tp3 = round(entry - atr * tp3_mult, 8)

        # Risk-level integrity is a hard safety contract. A malformed fallback
        # ladder must never reach ranking, live validation, or signal delivery.
        # TP1 must be on the profit side of entry and the ladder must progress
        # monotonically away from entry.
        levels = (sl, tp1, tp2, tp3)
        if not all(isinstance(v, (int, float)) and v == v and abs(v) != float("inf") for v in levels):
            return None
        if direction == "LONG":
            levels_valid = sl < entry < tp1 < tp2 < tp3
        else:
            levels_valid = tp3 < tp2 < tp1 < entry < sl
        if not levels_valid:
            return None

        sl_dist = abs(entry - sl)
        tp1_dist = abs(entry - tp1)
        if sl_dist <= 0 or sl_dist / entry < min_sl:
            return None
        rr = tp1_dist / sl_dist
        if rr < min_rr:
            return None

        return {
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": round(rr, 2),
        }
