import pandas as pd
from loaders.market_loader import MarketLoader
from config import CONFIG


class MarketDataLoader:

    def __init__(self):
        self.exchange = MarketLoader().get_exchange()

    def get_ohlcv(self, symbol, timeframe=None, limit=None):

        tf    = timeframe or CONFIG["timeframe"]
        lim   = limit     or CONFIG["ohlcv_limit"]

        data = self.exchange.fetch_ohlcv(symbol, timeframe=tf, limit=lim)

        df = pd.DataFrame(
            data,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        return df
