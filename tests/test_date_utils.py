"""Regression checks for publisher ISO dates used by the Nature crawler."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from utils import days, ymd


class PublisherDateTests(unittest.TestCase):
    def test_iso_dates_keep_month_and_day(self):
        for value in ('2026-10-07', '2026-10-01', '2026-09-30', '2026-07-10'):
            with self.subTest(value=value):
                self.assertEqual(ymd(value), value)

    def test_text_dates_match_publisher_iso_dates(self):
        for value in ('30 Sep 2026', '30 Sept 2026', '30 September 2026'):
            with self.subTest(value=value):
                self.assertEqual(ymd(value), '2026-09-30')

    def test_iso_timestamp_keeps_calendar_date(self):
        self.assertEqual(ymd('2026-10-07T12:00:00Z'), '2026-10-07')

    def test_week_boundary_does_not_drop_october_articles(self):
        self.assertGreaterEqual(days('2026-09-28', ymd('2026-10-01')), 0)
        self.assertLess(days('2026-09-28', ymd('2026-09-27')), 0)

    def test_invalid_iso_date_is_not_silently_reinterpreted(self):
        with self.assertRaises(ValueError):
            ymd('2026-13-01')


if __name__ == '__main__':
    unittest.main()
