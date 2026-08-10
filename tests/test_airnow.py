import unittest

from lib.airnow import parse_airnow_csv, parse_contours
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


if __name__ == '__main__':
    unittest.main()
