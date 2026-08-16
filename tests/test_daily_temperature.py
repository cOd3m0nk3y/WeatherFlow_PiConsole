from datetime import date, datetime
import unittest

import pytz

from lib.daily_temperature import (convert_temperature, forecast_series,
                                   observation_series, series_from,
                                   series_until)


class DailyTemperatureTests(unittest.TestCase):

    def setUp(self):
        self.timezone = pytz.timezone('America/Denver')
        self.day = date(2026, 8, 16)

    def timestamp(self, hour, minute=0):
        local = self.timezone.localize(datetime(2026, 8, 16, hour, minute))
        return int(local.timestamp())

    def test_extracts_forecast_for_local_day(self):
        hourly = [
            {'time': self.timestamp(0), 'air_temperature': 10},
            {'time': self.timestamp(12, 30), 'air_temperature': 20},
            {'time': self.timestamp(23), 'air_temperature': None},
            {'time': self.timestamp(0) + 86400, 'air_temperature': 11},
        ]

        result = forecast_series(hourly, self.day, self.timezone)

        self.assertEqual(result, [[0, 10.0], [12.5, 20.0]])

    def test_extracts_tempest_observation_index(self):
        observation = [None] * 8
        observation[0] = self.timestamp(6, 15)
        observation[7] = 12.5

        result = observation_series([observation], self.day, self.timezone, 7)

        self.assertEqual(result, [[self.timestamp(6, 15), 12.5]])

    def test_converts_temperature_units(self):
        self.assertEqual(convert_temperature(0, 'f'), 32)
        self.assertEqual(convert_temperature(10, 'c'), 10)
        self.assertIsNone(convert_temperature(None, 'f'))

    def test_splits_forecast_at_now_with_interpolated_boundary(self):
        points = [[12, 20], [13, 24], [14, 22]]

        self.assertEqual(series_until(points, 12.5),
                         [[12, 20], [12.5, 22]])
        self.assertEqual(series_from(points, 12.5),
                         [[12.5, 22], [13, 24], [14, 22]])

    def test_extends_cached_past_to_now_when_no_future_point_is_cached(self):
        self.assertEqual(series_until([[11, 18], [12, 20]], 12.7),
                         [[11, 18], [12, 20], [12.7, 20]])

    def test_starts_latest_at_now_when_api_begins_next_hour(self):
        self.assertEqual(series_from([[13, 24], [14, 22]], 12.7),
                         [[12.7, 24], [13, 24], [14, 22]])


if __name__ == '__main__':
    unittest.main()
