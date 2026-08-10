"""Pure slippy-map coordinate helpers shared by map-based panels."""

import math


def map_zoom(latitude, radius_miles):
    target_pixels = 430
    meters_per_pixel = radius_miles * 1609.344 * 2 / target_pixels
    zoom = math.log2(156543.03392 * math.cos(math.radians(latitude)) /
                     meters_per_pixel)
    return max(3, min(14, round(zoom)))


def map_tile(latitude, longitude, zoom):
    scale = 2 ** zoom
    x_float = (longitude + 180.0) / 360.0 * scale
    latitude_rad = math.radians(latitude)
    y_float = (1.0 - math.asinh(math.tan(latitude_rad)) / math.pi) / 2.0 * scale
    return int(x_float), int(y_float), x_float % 1, y_float % 1


def centered_crop(marker_x, marker_y, width=512, height=320):
    """Return a crop centered on a point in the middle tile of a 3x3 map."""
    center_x = (1 + marker_x) * 256
    center_y = (1 + marker_y) * 256
    return (round(center_x - width / 2), round(center_y - height / 2),
            round(center_x + width / 2), round(center_y + height / 2))
