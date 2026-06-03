from loaders.market_data_loader import (
    MarketDataLoader
)

loader = MarketDataLoader()

df = loader.get_ohlcv(
    "BTC/USDT:USDT"
)

print(df.tail())
