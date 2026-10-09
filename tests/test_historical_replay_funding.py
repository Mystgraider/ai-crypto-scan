"""Regression tests for historical funding archive loading and causality."""

import unittest
from unittest import mock

import pandas as pd

from tools import historical_replay as replay


def ms(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


class HistoricalFundingArchiveTests(unittest.TestCase):
    def test_fetches_monthly_archives_and_filters_exact_window(self):
        start_ms = ms("2026-09-30 00:00:00")
        end_ms = ms("2026-10-01 00:00:00")
        september = pd.DataFrame(
            {
                "calc_time": [
                    "2026-09-29 23:59:00",
                    "2026-09-30 00:00:00",
                    "2026-10-01 00:00:00",
                ],
                "last_funding_rate": [0.001, 0.002, 0.003],
            }
        )
        october = pd.DataFrame(
            {
                "calc_time": [
                    "2026-10-01 00:00:00",
                    "2026-10-02 00:00:00",
                ],
                "last_funding_rate": [0.003, 0.004],
            }
        )

        with mock.patch.object(
            replay, "_download_archive_csv", side_effect=[september, october]
        ) as download:
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(
            [call.args[0] for call in download.call_args_list],
            [
                "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                "ETHUSDT/ETHUSDT-fundingRate-2026-09.zip",
                "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                "ETHUSDT/ETHUSDT-fundingRate-2026-10.zip",
            ],
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(
            list(result["timestamp"]),
            [
                pd.Timestamp("2026-09-30 00:00:00", tz="UTC"),
                pd.Timestamp("2026-10-01 00:00:00", tz="UTC"),
            ],
        )
        self.assertEqual(list(result["fundingRate"]), [0.002, 0.003])

    def test_parses_epoch_millisecond_funding_timestamps(self):
        start_ms = ms("2026-09-01 00:00:00")
        end_ms = ms("2026-09-02 00:00:00")
        frame = pd.DataFrame(
            {
                "fundingTime": [start_ms, end_ms + 60_000],
                "fundingRate": [0.0015, 0.0025],
            }
        )

        with mock.patch.object(replay, "_download_archive_csv", return_value=frame):
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["timestamp"], pd.Timestamp(start_ms, unit="ms", tz="UTC"))
        self.assertEqual(result.iloc[0]["fundingRate"], 0.0015)

    def test_empty_or_unrecognized_archives_return_empty_schema(self):
        start_ms = ms("2026-09-01 00:00:00")
        end_ms = ms("2026-09-02 00:00:00")
        with mock.patch.object(
            replay, "_download_archive_csv", return_value=pd.DataFrame({"unexpected": [1]})
        ):
            result = replay.fetch_funding("ETHUSDT", start_ms, end_ms)

        self.assertEqual(list(result.columns), ["timestamp", "fundingRate"])
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
