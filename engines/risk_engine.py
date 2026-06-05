"""
Risk Engine — V5.4 fix
========================
FIXED: ATR multipliers now guarantee RR >= 2.0

Previous bug:
  SL = 1.5× ATR, TP1 = 2.0× ATR → RR = 1.33 (always failed min_rr=2.0)
  Result: 222/300 coins failed risk check → 0 signals

Fixed multipliers:
  SL = 1.0× ATR, TP1 = 2.5× ATR → RR = 2.5 ✅
  TP2 = 4.0× ATR, TP3 = 6.0× ATR

SL at 1×ATR = natural volatility boundary.
Price shouldn't cross 1 full ATR against you if the trend is real.
"""

from config import CONFIG


class RiskEngine:

    def calculate(self, direction: str, entry: float, atr: float) -> dict | None:

        sl_mult  = CONFIG["sl_atr_mult"]    # 1.0
        tp1_mult = CONFIG["tp1_atr_mult"]   # 2.5
        tp2_mult = CONFIG["tp2_atr_mult"]   # 4.0
        tp3_mult = CONFIG["tp3_atr_mult"]   # 6.0
        min_rr   = CONFIG["min_rr"]         # 2.0
        min_sl   = CONFIG["min_sl_pct"]     # 0.003

        if direction == "LONG":
            sl  = round(entry - atr * sl_mult,  8)
            tp1 = round(entry + atr * tp1_mult, 8)
            tp2 = round(entry + atr * tp2_mult, 8)
            tp3 = round(entry + atr * tp3_mult, 8)
        else:  # SHORT
            sl  = round(entry + atr * sl_mult,  8)
            tp1 = round(entry - atr * tp1_mult, 8)
            tp2 = round(entry - atr * tp2_mult, 8)
            tp3 = round(entry - atr * tp3_mult, 8)

        sl_dist  = abs(entry - sl)
        tp1_dist = abs(entry - tp1)

        # Guard: SL too small (coin barely moves)
        if entry > 0 and sl_dist / entry < min_sl:
            return None

        # Guard: RR below minimum
        if sl_dist == 0 or (tp1_dist / sl_dist) < min_rr:
            return None

        return {
            "entry": entry,
            "sl":    sl,
            "tp1":   tp1,
            "tp2":   tp2,
            "tp3":   tp3,
            "rr":    round(tp1_dist / sl_dist, 2),
        }
