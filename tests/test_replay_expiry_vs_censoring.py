"""Regression: a signal whose 72h window is only PARTLY covered by data (the replay
ran out of candles) is censored/unresolved (OPEN), not EXPIRED. In Run #68, 118 of
213 'EXPIRED' signals were younger than the 72h window at the end of the data."""
import unittest

import pandas as pd

from tools.historical_replay import historical_outcome

T0 = pd.Timestamp("2026-10-01T12:00:00Z")
FIVE = pd.Timedelta(minutes=5)


def quiet(n, first=1):
    ts = pd.to_datetime([T0 + FIVE * (first + i) for i in range(n)], utc=True)
    return pd.DataFrame({"timestamp": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1.0})


SIG = {"direction": "LONG", "entry": 100.0, "sl": 98.0, "tp1": 103.0, "tp2": 106.0, "tp3": 110.0,
       "_replay_time": T0.isoformat()}


class ExpiryVsCensoringTests(unittest.TestCase):
    def test_partial_coverage_is_open_not_expired(self):
        self.assertEqual(historical_outcome(SIG, quiet(10))["status"], "OPEN")                # 50 minutes of 72h
        self.assertEqual(historical_outcome(SIG, quiet(72 * 12 // 2))["status"], "OPEN")      # 36h of 72h

    def test_full_coverage_without_event_is_expired(self):
        self.assertEqual(historical_outcome(SIG, quiet(72 * 12))["status"], "EXPIRED")        # candles up to the 72h end

    def test_events_inside_partial_window_still_resolve(self):
        df = quiet(10)
        df.loc[5, ["high", "low"]] = [111.0, 99.5]
        self.assertEqual(historical_outcome(SIG, df)["status"], "TP3_HIT")

    def test_no_future_data_is_open(self):
        self.assertEqual(historical_outcome(SIG, quiet(0))["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
