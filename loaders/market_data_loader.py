"""
Market Data Loader — Phase 4 upgrade
=====================================
Supports multiple timeframes (1H and 4H).
Used by main scanner and MultiFrameEngine.

BTC fetch failures are converted into an explicit one-row unavailable
frame so the BTC safety filter can fail closed without hiding non-BTC
market-data failures.
"""

import pandas as pd
from loaders.market_loader import MarketLoader
from config import CONFIG


class MarketDataLoader:

    def __init__(self):
        self.exchange = MarketLoader().get_exchange()

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = None,
        limit: int = None
    ) -> pd.DataFrame:

        tf = timeframe or CONFIG["timeframe"]
        lim = limit or CONFIG["ohlcv_limit"]

        try:
            data = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=tf,
                limit=lim
            )
        except Exception:
            # BTC is a global safety dependency. If its market data is
            # unavailable, preserve an explicit marker and let BTCFilter
            # return UNKNOWN with both directions blocked. Never swallow
            # failures for ordinary coin data.
            if symbol == CONFIG["btc_symbol"]:
                fallback = pd.DataFrame(
                    [[0, 0.0, 0.0, 0.0, 0.0, 0.0]],
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                fallback["timestamp"] = pd.to_datetime(fallback["timestamp"], unit="ms")
                fallback.attrs["btc_data_unavailable"] = True
                fallback.attrs["btc_market_data"] = True
                return fallback
            raise

        df = pd.DataFrame(
            data,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        return df

    def get_4h(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 4H candles.

        V6.1.3 fix: default was 50, but Indicators.apply() requires
        MIN_CANDLES=60 — every Indicators.apply(get_4h(...)) call was
        raising ValueError("Insufficient candles: 50 < 60"), which
        silently fell back to MTF "PROXY" status on every signal.
        """
        return self.get_ohlcv(symbol, timeframe="4h", limit=limit)

    def get_1h(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 1H candles."""
        return self.get_ohlcv(symbol, timeframe="1h", limit=limit)

    def get_15m(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 15M candles — used for entry precision in MTF engine."""
        return self.get_ohlcv(symbol, timeframe="15m", limit=limit)

    def get_5m(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 5M candles — RRCE execution timeframe."""
        return self.get_ohlcv(symbol, timeframe="5m", limit=limit)
