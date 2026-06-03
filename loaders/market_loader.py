import ccxt

from config import CONFIG


class MarketLoader:

    def __init__(self):

        exchange_name = CONFIG[
            "exchange"
        ]

        if exchange_name == "okx":

            self.exchange = ccxt.okx({
                "enableRateLimit": True
            })

        elif exchange_name == "bitget":

            self.exchange = ccxt.bitget({
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap"
                }
            })

        else:

            raise ValueError(
                f"Unsupported exchange: "
                f"{exchange_name}"
            )

    def get_exchange(self):

        return self.exchange

    def load_markets(self):

        return self.exchange.load_markets()
