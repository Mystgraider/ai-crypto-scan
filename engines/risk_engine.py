"""
Risk Engine — V5.5
====================
Direction-aware SL sizing:

LONG  → SL = 1.0× ATR  (normal, price doesn't usually wick 1 ATR against trend)
SHORT → SL = 2.0× ATR  (wider, bear market bounces are violent and fast)

Why SHORT needs wider SL:
  In a downtrend, BTC bounces 1-2% regularly (dead cat)
  Alts bounce 2-4% due to higher beta
  1× ATR SL = ~1-2% = gets hit on normal bounce
  2× ATR SL = ~2-4% = survives normal bounce, continues down after

TP adjusted to maintain RR >= 2.0:
  LONG:  SL=1.0×, TP1=2.5×  → RR=2.5
  SHORT: SL=2.0×, TP1=4.5×  → RR=2.25
"""

from config import CONFIG


class RiskEngine:

    def calculate(self, direction: str, entry: float, atr: float) -> dict | None:

        min_rr = CONFIG["min_rr"]    # 2.0
        min_sl = CONFIG["min_sl_pct"]  # 0.003

        if direction == "LONG":
            sl_mult  = CONFIG["sl_atr_mult"]     # 1.0
            tp1_mult = CONFIG["tp1_atr_mult"]    # 2.5
            tp2_mult = CONFIG["tp2_atr_mult"]    # 4.0
            tp3_mult = CONFIG["tp3_atr_mult"]    # 6.0
        else:
            # SHORT: wider SL to survive dead cat bounces
            sl_mult  = CONFIG["short_sl_atr_mult"]   # 2.0
            tp1_mult = CONFIG["short_tp1_atr_mult"]  # 4.5
            tp2_mult = CONFIG["short_tp2_atr_mult"]  # 6.0
            tp3_mult = CONFIG["short_tp3_atr_mult"]  # 8.0

        if direction == "LONG":
            sl  = round(entry - atr * sl_mult,  8)
            tp1 = round(entry + atr * tp1_mult, 8)
            tp2 = round(entry + atr * tp2_mult, 8)
            tp3 = round(entry + atr * tp3_mult, 8)
        else:
            sl  = round(entry + atr * sl_mult,  8)
            tp1 = round(entry - atr * tp1_mult, 8)
            tp2 = round(entry - atr * tp2_mult, 8)
            tp3 = round(entry - atr * tp3_mult, 8)

        sl_dist  = abs(entry - sl)
        tp1_dist = abs(entry - tp1)

        if entry > 0 and sl_dist / entry < min_sl:
            return None

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
