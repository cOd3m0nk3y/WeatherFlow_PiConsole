import unittest

from PIL import Image, ImageDraw

from lib.radar import (draw_house_marker, expanded_radius, mercator_mosaic_bbox,
                       precipitation_coverage, radar_status, radar_wms_url,
                       radar_catalog_url, radar_frame_url, select_hour_frames,
                       zoom_levels)


class RadarTests(unittest.TestCase):
    def test_mosaic_bbox_has_three_tile_spans(self):
        left, bottom, right, top = mercator_mosaic_bbox(9, 106, 194)
        tile_span = 40075016.685578488 / (2 ** 9)
        self.assertAlmostEqual(right - left, tile_span * 3)
        self.assertAlmostEqual(top - bottom, tile_span * 3)

    def test_wms_request_uses_official_reflectivity_layer(self):
        url = radar_wms_url(9, 106, 194)
        self.assertIn('opengeo.ncep.noaa.gov', url)
        self.assertIn('layers=conus_bref_qcd', url)
        self.assertIn('srs=EPSG%3A3857', url)
        self.assertIn('transparent=true', url)

    def test_reports_clear_when_local_radar_crop_is_transparent(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((0, 0, 20, 20), fill=(255, 0, 0, 255))
        self.assertEqual(radar_status(overlay, (128, 128, 640, 448)),
                         'No precipitation detected')

    def test_reports_echoes_inside_local_radar_crop(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((375, 280, 394, 289),
                                          fill=(255, 0, 0, 255))
        self.assertEqual(radar_status(overlay, (128, 128, 640, 448)),
                         'NWS base reflectivity')

    def test_ignores_isolated_radar_artifact_pixels(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        drawing = ImageDraw.Draw(overlay)
        for point in ((300, 200), (301, 201), (302, 202)):
            drawing.point(point, fill=(255, 0, 0, 255))
        self.assertEqual(radar_status(overlay, (128, 128, 640, 448)),
                         'No precipitation detected')

    def test_zoom_continues_for_barely_visible_coverage(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((300, 200, 309, 209),
                                          fill=(0, 160, 255, 255))
        self.assertEqual(radar_status(overlay, (128, 128, 640, 448)),
                         'No precipitation detected')

    def test_zoom_continues_when_echo_is_clipped_at_map_edge(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((128, 180, 135, 195),
                                          fill=(0, 160, 255, 255))
        self.assertEqual(radar_status(overlay, (128, 128, 640, 448)),
                         'No precipitation detected')

    def test_formats_very_low_precipitation_coverage(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((128, 180, 135, 195),
                                          fill=(0, 160, 255, 255))
        self.assertEqual(precipitation_coverage(
            overlay, (128, 128, 640, 448)), '<0.1%')

    def test_formats_clear_precipitation_coverage(self):
        overlay = Image.new('RGBA', (768, 768), (0, 0, 0, 0))
        self.assertEqual(precipitation_coverage(
            overlay, (128, 128, 640, 448)), '0%')

    def test_selects_distinct_frames_from_latest_hour(self):
        latest = 1_786_372_000_000
        catalog = {'features': [
            {'attributes': {'idp_validtime': latest - offset}}
            for offset in (0, 1_000, 300_000, 600_000, 3_300_000,
                           3_900_000)]}
        self.assertEqual(select_hour_frames(catalog),
                         [latest - 3_300_000, latest - 600_000,
                          latest - 300_000, latest])

    def test_time_service_urls_use_catalog_and_frame_timestamp(self):
        self.assertIn('/query?', radar_catalog_url(8, 53, 97))
        frame_url = radar_frame_url(8, 53, 97, 1_786_372_000_000)
        self.assertIn('/exportImage?', frame_url)
        self.assertIn('time=1786372000000', frame_url)

    def test_radius_doubles_for_each_automatic_zoom_step(self):
        self.assertEqual(expanded_radius(50, 8, 8), 50)
        self.assertEqual(expanded_radius(50, 8, 6), 200)

    def test_zero_zoom_limit_searches_all_available_levels(self):
        self.assertEqual(list(zoom_levels(8, 0)), [8, 7, 6, 5, 4, 3])

    def test_positive_zoom_limit_caps_expansion(self):
        self.assertEqual(list(zoom_levels(8, 1)), [8, 7])
        self.assertEqual(list(zoom_levels(8, 2)), [8, 7, 6])

    def test_house_marker_uses_console_blue_at_map_center(self):
        image = Image.new('RGBA', (512, 320), (0, 0, 0, 255))
        draw_house_marker(image)
        self.assertEqual(image.getpixel((256, 160)), (0, 164, 180, 255))
        self.assertEqual(image.getpixel((256, 165)), (17, 17, 17, 255))
        self.assertEqual(image.getpixel((256, 170)), (255, 255, 255, 255))
        self.assertEqual(image.getpixel((256, 175)), (0, 0, 0, 255))


if __name__ == '__main__':
    unittest.main()
