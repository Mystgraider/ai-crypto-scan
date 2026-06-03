from config import CONFIG

from database import Database

from logger import logger

from state_manager import StateManager

from engines.oi_engine import OIEngine

from engines.market_regime import (
    MarketRegimeEngine
)

from engines.funding_engine import (
    FundingEngine
)

from weighted_score_engine import (
    WeightedScoreEngine
)


class ScannerCore:

    def __init__(self):

        self.config = CONFIG

        self.db = Database()

        self.state = StateManager()

        self.oi_engine = OIEngine()

        self.regime_engine = (
            MarketRegimeEngine()
        )

        self.funding_engine = (
            FundingEngine()
        )

        self.score_engine = (
            WeightedScoreEngine()
        )

        logger.info(
            "Scanner Core Initialized"
        )

    def status(self):

        return {

            "strategy_version":
            self.config[
                "strategy_version"
            ],

            "min_score":
            self.config[
                "min_score"
            ],

            "top_coins":
            self.config[
                "top_coins_limit"
            ]
        }


if __name__ == "__main__":

    scanner = ScannerCore()

    print(
        scanner.status()
    )
