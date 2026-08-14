import unittest
from datetime import datetime, timezone

from PIL import Image

from lib.airnow import (area_tint, contour_hours, format_observed,
                        is_rate_limited, parse_airnow_csv, parse_contours,
                        preserve_map_state, refresh_minutes)
from lib.map_utils import centered_crop, map_tile, map_zoom


class AirNowTests(unittest.TestCase):
    def test_selects_highest_pollutant_aqi(self):
        text = ('DateObserved,HourObserved,ReportingArea,StateCode,ParameterName,AQI\n'
                '2026-08-10,7,Castle Rock,CO,O3,42\n'
                '2026-08-10,7,Castle Rock,CO,PM2.5,63\n')
        result = parse_airnow_csv(text)
        self.assertEqual(result['AQI'], '63')
        self.assertEqual(result['Category'], 'Moderate')
        self.assertEqual(result['Pollutant'], 'PM2.5')
        self.assertEqual(result['Color'], 'ffff00ff')

    def test_formats_airnow_publication_time_with_zone(self):
        observed = format_observed({'DateObserved': '2026-08-11',
                                    'HourObserved': '7',
                                    'LocalTimeZone': 'MST'})
        self.assertEqual(observed, 'Aug 11 07:00 MST')

    def test_formats_airnow_publication_time_as_12_hour(self):
        observed = format_observed({'DateObserved': '2026-08-11',
                                    'HourObserved': '19:00',
                                    'LocalTimeZone': 'MDT'}, '12 hr')
        self.assertEqual(observed, 'Aug 11 7:00 PM MDT')

    def test_formats_airnow_publication_time_with_seconds(self):
        observed = format_observed({'DateObserved': '2026-08-11',
                                    'HourObserved': '07:30:00',
                                    'LocalTimeZone': 'MDT'}, '12 hr')
        self.assertEqual(observed, 'Aug 11 7:30 AM MDT')

    def test_larger_radius_uses_lower_zoom(self):
        self.assertGreater(map_zoom(39.4, 10), map_zoom(39.4, 100))

    def test_map_marker_stays_within_tile(self):
        _, _, marker_x, marker_y = map_tile(39.37399, -104.81092, 9)
        self.assertGreaterEqual(marker_x, 0)
        self.assertLess(marker_x, 1)
        self.assertGreaterEqual(marker_y, 0)
        self.assertLess(marker_y, 1)

    def test_centered_crop_places_station_at_image_center(self):
        marker_x, marker_y = .347, .812
        left, top, right, bottom = centered_crop(marker_x, marker_y)
        station_x = (1 + marker_x) * 256 - left
        station_y = (1 + marker_y) * 256 - top
        self.assertAlmostEqual(station_x, (right - left) / 2, delta=.5)
        self.assertAlmostEqual(station_y, (bottom - top) / 2, delta=.5)

    def test_parses_airnow_kml_color_and_polygon(self):
        kml = b'''<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
        <Style id="good"><PolyStyle><color>aa00e400</color></PolyStyle></Style>
        <Placemark><styleUrl>#good</styleUrl><Polygon><outerBoundaryIs><LinearRing>
        <coordinates>-105,39,0 -104,39,0 -104,40,0</coordinates>
        </LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
        contours = parse_contours(kml)
        self.assertEqual(contours[0][0], (0, 228, 0, 170))
        self.assertEqual(len(contours[0][1]), 3)

    def test_normalizes_airnow_epsg4326_axis_order(self):
        kml = b'''<kml><Document><Placemark><Polygon><LinearRing>
        <coordinates>39.1,-105.2,0 39.2,-105.1,0 39.3,-105.0,0</coordinates>
        </LinearRing></Polygon></Placemark></Document></kml>'''
        points = parse_contours(kml)[0][1]
        self.assertEqual(points[0], (-105.2, 39.1))

    def test_uses_older_contour_hour_early_in_hour(self):
        now = datetime(2026, 8, 14, 13, 10, tzinfo=timezone.utc)
        self.assertEqual(contour_hours(now), ['2026081411'])

    def test_bounds_contour_fallback_to_two_hours(self):
        now = datetime(2026, 8, 14, 13, 45, tzinfo=timezone.utc)
        self.assertEqual(contour_hours(now), ['2026081412', '2026081411'])

    def test_recognizes_airnow_rate_limit(self):
        error = type('RateLimit', (), {'code': 429})()
        self.assertTrue(is_rate_limited(error=error))

    def test_area_tint_uses_aqi_color(self):
        image = Image.new('RGBA', (1, 1), (0, 0, 0, 255))
        tinted = area_tint(image, '00e400ff')
        red, green, blue, _alpha = tinted.getpixel((0, 0))
        self.assertEqual(red, 0)
        self.assertGreater(green, 0)
        self.assertEqual(blue, 0)

    def test_airnow_refresh_never_runs_more_than_hourly(self):
        self.assertEqual(refresh_minutes('15'), 60)
        self.assertEqual(refresh_minutes('120'), 120)

    def test_observation_refresh_preserves_complete_map_state(self):
        observation = {'AQI': '34'}
        result = preserve_map_state(
            observation, {'Map': 'cache/map.png',
                          'MapStatus': 'Area AQI tint'})
        self.assertEqual(result['Map'], 'cache/map.png')
        self.assertEqual(result['MapStatus'], 'Area AQI tint')
        self.assertEqual(result['MarkerX'], .5)
        self.assertEqual(result['MarkerY'], .5)


if __name__ == '__main__':
    unittest.main()
