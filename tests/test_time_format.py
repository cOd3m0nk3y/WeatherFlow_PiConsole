import unittest
from datetime import datetime

from lib.time_format import format_clock


class TimeFormatTests(unittest.TestCase):
    def test_formats_24_hour_time(self):
        self.assertEqual(format_clock(datetime(2026, 8, 11, 7, 5), '24 hr'),
                         '07:05')

    def test_formats_12_hour_time_without_leading_zero(self):
        self.assertEqual(format_clock(datetime(2026, 8, 11, 19, 5), '12 hr'),
                         '7:05 PM')


if __name__ == '__main__':
    unittest.main()
