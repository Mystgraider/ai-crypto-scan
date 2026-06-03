from loaders.market_loader import (
    MarketLoader
)

loader = MarketLoader()

markets = loader.load_markets()

print(
    f"Markets Loaded: "
    f"{len(markets)}"
)
