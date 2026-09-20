"""Market data access with per-scan request deduplication."""

import pandas as pd

from loaders.market_loader import MarketLoader
from config import CONFIG


class MarketDataLoader:
    """Fetch exchange candles and reuse successful results within one scan cycle.

    One MarketDataLoader instance is intentionally scoped to a single scanner run.
    The cache is keyed by symbol, timeframe, and limit, so repeated requests for
    the same market context do not create duplicate exchange API calls.
    Cached frames are copied before returning so downstream indicator processing
    cannot mutate the cached raw data.
    """

    def __init__(self):
        self.exchange = MarketLoader().get_exchange()
        self._ohlcv_cache: dict[tuple[str, str, int], pd.DataFrame] = {}

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = None,
        limit: int = None,
    ) -> pd.DataFrame:
        tf = timeframe or CONFIG["timeframe"]
        lim = limit if limit is not None else CONFIG["ohlcv_limit"]
        key = (symbol, tf, int(lim))

        cached = self._ohlcv_cache.get(key)
        if cached is not None:
            return cached.copy(deep=True)

        try:
            data = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=tf,
                limit=lim,
            )
        except Exception:
            if symbol == CONFIG["btc_symbol"] and tf == "1h":
                df = pd.DataFrame(
                    [[
                        pd.Timestamp.utcnow(),
                        float("nan"),
                        float("nan"),
                        float("nan"),
                        float("nan"),
                        float("nan"),
                    ]],
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df.attrs["btc_data_unavailable"] = True
                df.attrs["btc_market_data"] = True
                self._ohlcv_cache[key] = df
                return df.copy(deep=True)
            raise

        df = pd.DataFrame(
            data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        if symbol == CONFIG["btc_symbol"]:
            df.attrs["btc_market_data"] = True

        self._ohlcv_cache[key] = df
        return df.copy(deep=True)

    def get_4h(self, symbol: str, limit: int = None) -> pd.DataFrame:
        """Return the configured safe 4H candle window."""
        effective_limit = (
            CONFIG["ohlcv_4h_limit"] if limit is None else limit
        )
        return self.get_ohlcv(symbol, timeframe="4h", limit=effective_limit)

    def get_1h(self, symbol: str, limit: int = None) -> pd.DataFrame:
        """Return the configured 1H candle window."""
        effective_limit = CONFIG["ohlcv_limit"] if limit is None else limit
        return self.get_ohlcv(symbol, timeframe="1h", limit=effective_limit)

    def get_15m(self, symbol: str, limit: int = None) -> pd.DataFrame:
        """Return the configured 15M candle window."""
        effective_limit = CONFIG["ohlcv_limit"] if limit is None else limit
        return self.get_ohlcv(symbol, timeframe="15m", limit=effective_limit)

    def get_5m(self, symbol: str, limit: int = None) -> pd.DataFrame:
        """Return the configured 5M candle window."""
        effective_limit = CONFIG["ohlcv_limit"] if limit is None else limit
        return self.get_ohlcv(symbol, timeframe="5m", limit=effective_limit)
