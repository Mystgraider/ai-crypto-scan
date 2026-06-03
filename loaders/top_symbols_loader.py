from config import CONFIG
from loaders.market_loader import MarketLoader


class TopSymbolsLoader:

    def __init__(self):

        self.loader = MarketLoader()

        self.exchange = (
            self.loader.get_exchange()
        )

    def get_top_symbols(self):

        markets = (
            self.exchange.load_markets()
        )

        symbols = []

        for symbol, market in markets.items():

            try:

                if not market.get(
                    "active",
                    True
                ):
                    continue

                if "/USDT" not in symbol:
                    continue

                if not (
                    market.get("swap")
                    or
                    market.get("future")
                ):
                    continue

                symbols.append(
                    symbol
                )

            except:

                continue

        return sorted(
            symbols
        )[
            :CONFIG[
                "top_coins_limit"
            ]
        ]
