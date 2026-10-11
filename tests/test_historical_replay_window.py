"""Tests for deterministic fixed-window selection in historical replay."""

import os
import unittest
from unittest import mock

import pandas as pd

from tools.historical_replay import resolve_replay_end


class ReplayWindowTests(unittest.TestCase):
    def test_fixed_end_is_normalized_to_utc(self):
        with mock.patch.dict(os.environ, {"BACKTEST_END": "2026-10-12T08:00:00+08:00"}):
            self.assertEqual(
                resolve_replay_end(),
                pd.Timestamp("2026-10-12T00:00:00Z"),
            )

    def test_fixed_end_accepts_utc_z_suffix(self):
        with mock.patch.dict(os.environ, {"BACKTEST_END": "2026-10-12T00:00:00Z"}):
            self.assertEqual(
                resolve_replay_end(),
                pd.Timestamp("2026-10-12T00:00:00Z"),
            )

    def test_fixed_end_rejects_non_hour_boundary(self):
        with mock.patch.dict(os.environ, {"BACKTEST_END": "2026-10-12T00:05:00Z"}):
            with self.assertRaisesRegex(ValueError, "whole UTC hour"):
                resolve_replay_end()

    def test_empty_fixed_end_uses_last_completed_hour(self):
        with mock.patch.dict(os.environ, {"BACKTEST_END": ""}):
            self.assertEqual(
                resolve_replay_end(now="2026-10-12T03:42:00Z"),
                pd.Timestamp("2026-10-12T02:00:00Z"),
            )


if __name__ == "__main__":
    unittest.main()
