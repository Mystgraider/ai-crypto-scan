from loaders.market_data_loader import (
    MarketDataLoader
)

from indicators import Indicators

loader = MarketDataLoader()

df = loader.get_ohlcv(
    "BTC/USDT:USDT"
)

df = Indicators.apply(df)

print(
    df[
        [
            "close",
            "ema20",
            "ema50",
            "rsi",
            "atr",
            "rel_volume"
        ]
    ].tail()
)
