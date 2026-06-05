from config import CONFIG
from loaders.market_loader import MarketLoader


class TopSymbolsLoader:

    def __init__(self):
        self.exchange = MarketLoader().get_exchange()

    def get_top_symbols(self):

        markets = self.exchange.load_markets()
        candidates = []

        for symbol, market in markets.items():

            try:
                if not market.get("active", True):
                    continue

                if "/USDT" not in symbol:
                    continue

                if not (market.get("swap") or market.get("future")):
                    continue

                volume = float(
                    market.get("info", {}).get("quoteVolume") or
                    market.get("quoteVolume") or 0
                )

                candidates.append((symbol, volume))

            except Exception:
                continue

        # Sort by 24h quote volume descending → true top symbols
        candidates.sort(key=lambda x: x[1], reverse=True)

        limit = CONFIG["top_coins_limit"]
        return [s for s, _ in candidates[:limit]]
