import unittest
from datetime import datetime, timezone

from lib.extended_forecast import empty_days, normalize_daily_forecast


class ExtendedForecastTests(unittest.TestCase):

    def test_normalizes_and_pads_weatherflow_days(self):
        timestamp = int(datetime(2026, 8, 9, 6, tzinfo=timezone.utc).timestamp())
        result = normalize_daily_forecast([{
            'day_start_local': timestamp,
            'conditions': 'partly cloudy',
            'icon': 'partly-cloudy-day',
            'air_temp_high': 25,
            'air_temp_low': 10,
            'precip_probability': 27.6,
        }], 'America/Denver', 'f', count=3)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['day'], 'Today')
        self.assertEqual(result[0]['date'], 'Aug 9')
        self.assertEqual(result[0]['conditions'], 'Partly cloudy')
        self.assertEqual(result[0]['icon'], 'partly-cloudy-day')
        self.assertEqual(result[0]['high'], '77℉')
        self.assertEqual(result[0]['low'], '50℉')
        self.assertEqual(result[0]['precip'], '28%')
        self.assertEqual(result[1]['icon'], '-')

    def test_replaces_unknown_icon(self):
        result = normalize_daily_forecast([{
            'conditions': 'strange weather',
            'icon': 'not-an-icon',
            'air_temp_high': None,
            'air_temp_low': None,
        }], 'UTC', 'c', count=1)

        self.assertEqual(result[0]['icon'], '-')
        self.assertEqual(result[0]['high'], '-℃')
        self.assertEqual(result[0]['precip'], '0%')

    def test_empty_days_are_independent(self):
        days = empty_days(2)
        days[0]['day'] = 'Changed'
        self.assertEqual(days[1]['day'], '--')


if __name__ == '__main__':
    unittest.main()
