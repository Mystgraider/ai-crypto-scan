import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from storage import rrce_watchlist


class RRCEWatchlistTests(unittest.TestCase):
    def test_records_and_expires_stage2_setup(self):
        now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        stage1 = {"range_low": 90.0, "range_high": 110.0}
        stage2 = {"pool_level": 91.0, "sweep_extreme": 89.5}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            rrce_watchlist, "WATCHLIST_FILE", str(Path(directory) / "watchlist.json")
        ):
            count = rrce_watchlist.record_stage2_setup(
                "BTC/USDT:USDT", "LONG", "RANGE", stage1, stage2, 4, now
            )
            self.assertEqual(count, 1)
            self.assertEqual(rrce_watchlist.active_count(4, now + timedelta(hours=3)), 1)
            self.assertEqual(rrce_watchlist.active_count(4, now + timedelta(hours=5)), 0)

    def test_repeated_setup_updates_existing_entry(self):
        now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        stage1 = {"range_low": 90.0, "range_high": 110.0}
        stage2 = {"pool_level": 91.0, "sweep_extreme": 89.5}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            rrce_watchlist, "WATCHLIST_FILE", str(Path(directory) / "watchlist.json")
        ):
            rrce_watchlist.record_stage2_setup("BTC/USDT:USDT", "LONG", "RANGE", stage1, stage2, 4, now)
            rrce_watchlist.record_stage2_setup(
                "BTC/USDT:USDT", "LONG", "RANGE", stage1, stage2, 4, now + timedelta(minutes=15)
            )
            entries = rrce_watchlist._load()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries["BTC/USDT:USDT|LONG"]["observations"], 2)
