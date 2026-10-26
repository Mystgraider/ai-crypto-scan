"""
Open Interest Engine — V6.9.25
==============================
Calculates OI confirmation when data is available.

Unavailable OI is explicitly marked unavailable. It is not represented as
NEUTRAL because NEUTRAL means the market was actually observed and did not
meet a directional OI condition.

OI is supporting evidence, not a production hard gate. When an exchange
cannot provide current/history OI, the scanner must be allowed to continue
with an explicit UNAVAILABLE OI result and zero score adjustment.
"""


class OIEngine:

    def analyze(
        self,
        current_oi: float,
        previous_oi: float,
        price_change: float,
        direction: str,
    ) -> dict:
        if previous_oi <= 0 or current_oi <= 0:
            return self._unavailable("invalid_oi_values")

        oi_change_pct = ((current_oi - previous_oi) / previous_oi) * 100
        oi_rising = oi_change_pct > 0.5
        oi_falling = oi_change_pct < -0.5
        price_down = price_change < -0.1
        price_up = price_change > 0.1

        if direction == "SHORT":
            if price_down and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            if price_down and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            if price_up and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)
        else:
            if price_up and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            if price_up and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            if price_down and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)

        return self._result("NEUTRAL", 0, oi_change_pct)

    @staticmethod
    def _result(label, score_adj, oi_change_pct):
        return {
            "available": True,
            "data_available": True,
            "oi_signal": label,
            "score_adj": score_adj,
            "oi_change_pct": round(oi_change_pct, 2),
        }

    @staticmethod
    def _unavailable(reason):
        return {
            "available": False,
            "data_available": False,
            "oi_signal": "UNAVAILABLE",
            "score_adj": 0,
            "oi_change_pct": None,
            "reason": reason,
        }

    @staticmethod
    def _read_oi_value(payload):
        """Return (value, field_path) without silently mixing OI units.

        CCXT may expose OI as quote-currency value or contract/base amount.
        A current observation and its historical comparator must use the
        same field path; if history lacks that field, report unavailable.
        """
        if not isinstance(payload, dict):
            return None, None

        for key in ("openInterestValue", "openInterest", "openInterestAmount"):
            value = payload.get(key)
            if value is not None and value != "":
                return value, key

        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("holdVol", "oi"):
                value = info.get(key)
                if value is not None and value != "":
                    return value, "info." + key

        return None, None

    @staticmethod
    def _read_matching_oi_value(payload, field_path):
        """Read only the same field used by the current OI observation."""
        if not isinstance(payload, dict) or not field_path:
            return None
        if field_path.startswith("info."):
            info = payload.get("info")
            return info.get(field_path.split(".", 1)[1]) if isinstance(info, dict) else None
        return payload.get(field_path)

    def fetch_oi(self, exchange, symbol: str) -> dict:
        """Fetch OI without making OI availability a signal-discovery gate."""
        try:
            oi_data = exchange.fetch_open_interest(symbol)
            current_raw, current_field = self._read_oi_value(oi_data)
            if current_raw is None:
                return self._soft_unavailable(reason="current_oi_missing")

            try:
                current_oi = float(current_raw)
            except (TypeError, ValueError, OverflowError):
                return self._soft_unavailable(reason="invalid_current_oi")

            if current_oi <= 0:
                return self._soft_unavailable(
                    current_oi=current_oi,
                    reason="invalid_current_oi",
                )

            try:
                history = exchange.fetch_open_interest_history(
                    symbol, timeframe="1h", limit=2
                )
                if not history or len(history) < 2:
                    return self._soft_unavailable(
                        current_oi=current_oi,
                        reason="oi_history_unavailable",
                    )

                prev_raw = self._read_matching_oi_value(history[-2], current_field)
                if prev_raw is None:
                    return self._soft_unavailable(
                        current_oi=current_oi,
                        reason="previous_oi_missing_or_unit_mismatch",
                    )
                try:
                    previous_oi = float(prev_raw)
                except (TypeError, ValueError, OverflowError):
                    return self._soft_unavailable(
                        current_oi=current_oi,
                        reason="invalid_previous_oi",
                    )
            except Exception:
                return self._soft_unavailable(
                    current_oi=current_oi,
                    reason="oi_history_fetch_error",
                )

            if previous_oi <= 0:
                return self._soft_unavailable(
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    reason="invalid_previous_oi",
                )

            return {
                "current_oi": current_oi,
                "previous_oi": previous_oi,
                "available": True,
                "data_available": True,
            }

        except Exception as e:
            print(f"  ⚠️  OI fetch failed {symbol}: {e}")
            return self._soft_unavailable(reason="fetch_error")

    @staticmethod
    def _soft_unavailable(current_oi=0, previous_oi=0, reason="unknown"):
        return {
            "current_oi": current_oi,
            "previous_oi": previous_oi,
            "available": False,
            "data_available": False,
            "reason": reason,
        }
