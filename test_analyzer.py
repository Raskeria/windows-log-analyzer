import unittest
from datetime import datetime, timedelta, timezone
from analyzer import busiest_window, THRESHOLD


class TimeWindowTests(unittest.TestCase):
    def check_window(self, seconds, expected_count, expected_alert):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(seconds=s) for s in seconds]

        count, start, end = busiest_window(timestamps)

        self.assertEqual(count, expected_count)
        self.assertEqual(count >= THRESHOLD, expected_alert)

        if timestamps:
            self.assertLessEqual(end - start, timedelta(minutes=5))
        else:
            self.assertIsNone(start)
            self.assertIsNone(end)

    def test_three_close_events(self):
        self.check_window([0, 60, 120], 3, True)

    def test_two_events_below_threshold(self):
        self.check_window([0, 60], 2, False)

    def test_spread_out_events(self):
        self.check_window([0, 360, 720], 1, False)

    def test_exactly_five_minutes(self):
        self.check_window([0, 150, 300], 3, True)

    def test_outside_five_minutes(self):
        self.check_window([0, 150, 301], 2, False)

    def test_unsorted_events(self):
        self.check_window([120, 0, 60], 3, True)

    def test_empty_input(self):
        self.check_window([], 0, False)


if __name__ == "__main__":
    unittest.main()