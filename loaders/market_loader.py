import ccxt
from config import CONFIG


class MarketLoader:

    def __init__(self):

        name = CONFIG["exchange"]

        if name == "okx":
            self.exchange = ccxt.okx({
                "enableRateLimit": True
            })

        elif name == "bitget":
            self.exchange = ccxt.bitget({
                "enableRateLimit": True,
                "options": {"defaultType": "swap"}
            })

        else:
            raise ValueError(f"Unsupported exchange: {name}")

    def get_exchange(self):
        return self.exchange
