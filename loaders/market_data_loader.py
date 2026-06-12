"""
Market Data Loader — Phase 4 upgrade
=====================================
Supports multiple timeframes (1H and 4H).
Used by main scanner and MultiFrameEngine.
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

        tf  = timeframe or CONFIG["timeframe"]
        lim = limit     or CONFIG["ohlcv_limit"]

        data = self.exchange.fetch_ohlcv(
            symbol,
            timeframe=tf,
            limit=lim
        )

        df = pd.DataFrame(
            data,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        return df

    def get_4h(self, symbol: str, limit: int = 50) -> pd.DataFrame:
        """Convenience method for 4H candles."""
        return self.get_ohlcv(symbol, timeframe="4h", limit=limit)

    def get_1h(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 1H candles."""
        return self.get_ohlcv(symbol, timeframe="1h", limit=limit)

    def get_15m(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """Convenience method for 15M candles — used for entry precision in MTF engine."""
        return self.get_ohlcv(symbol, timeframe="15m", limit=limit)
