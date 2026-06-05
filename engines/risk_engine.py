from config import CONFIG


class RiskEngine:

    def calculate(self, direction: str, entry: float, atr: float) -> dict | None:
        """
        Returns risk levels or None if the setup fails minimum RR.
        """

        sl_mult  = CONFIG["sl_atr_mult"]
        tp1_mult = CONFIG["tp1_atr_mult"]
        tp2_mult = CONFIG["tp2_atr_mult"]
        tp3_mult = CONFIG["tp3_atr_mult"]
        min_rr   = CONFIG["min_rr"]
        min_sl   = CONFIG["min_sl_pct"]

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

        # Guard: SL too small
        if sl_dist / entry < min_sl:
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
            "rr":    round(tp1_dist / sl_dist, 2)
        }
