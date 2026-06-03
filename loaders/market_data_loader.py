import pandas as pd

from loaders.market_loader import (
    MarketLoader
)


class MarketDataLoader:

    def __init__(self):

        self.loader = MarketLoader()

        self.exchange = (
            self.loader.get_exchange()
        )

    def get_ohlcv(
        self,
        symbol,
        timeframe="1h",
        limit=100
    ):

        data = self.exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=limit
        )

        df = pd.DataFrame(

            data,

            columns=[

                "timestamp",

                "open",

                "high",

                "low",

                "close",

                "volume"
            ]
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms"
        )

        return df
