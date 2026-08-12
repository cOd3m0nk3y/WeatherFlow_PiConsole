"""AirNow observations and map state for PiConsole."""

import csv
import io
import math
import os
import ssl
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

import certifi
from kivy.app import App
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.network.urlrequest import UrlRequest

from lib.map_utils import centered_crop, map_tile, map_zoom


AQI_CATEGORIES = ((50, 'Good', '00e400ff'), (100, 'Moderate', 'ffff00ff'),
                  (150, 'Unhealthy for Sensitive Groups', 'ff7e00ff'),
                  (200, 'Unhealthy', 'ff0000ff'), (300, 'Very Unhealthy', '8f3f97ff'),
                  (500, 'Hazardous', '7e0023ff'))


def empty_air_quality(status='Waiting for AirNow'):
    return {'AQI': '--', 'Category': 'Unavailable', 'Pollutant': '--', 'Area': '--',
            'Observed': '--', 'Updated': '--', 'Color': '404040ff',
            'Status': status, 'Map': '', 'MarkerX': .5, 'MarkerY': .5}


def format_observed(row):
    date = str(row.get('DateObserved', '')).strip()
    try:
        date = datetime.strptime(date, '%Y-%m-%d').strftime('%b %d')
    except ValueError:
        pass
    raw_hour = str(row.get('HourObserved', '')).strip()
    try:
        hour = '{:02d}:00'.format(int(float(raw_hour)))
    except ValueError:
        hour = raw_hour
    zone = str(row.get('LocalTimeZone', '')).strip()
    return ' '.join(value for value in (date, hour, zone) if value) or '--'


def parse_airnow_csv(text):
    rows = list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
    valid = []
    for row in rows:
        raw = row.get('NowcastAQI', row.get('AQI', ''))
        try:
            valid.append((int(float(raw)), row))
        except (TypeError, ValueError):
            continue
    if not valid:
        raise ValueError('No valid AQI observation returned')
    aqi, row = max(valid, key=lambda item: item[0])
    category, color = next(((name, color) for limit, name, color in AQI_CATEGORIES
                            if aqi <= limit), ('Beyond AQI', '7e0023ff'))
    observed = format_observed(row)
    area = row.get('ReportingAreaName', row.get('ReportingArea', '--'))
    state = row.get('StateCode', '')
    if state:
        area = '{}, {}'.format(area, state)
    return {'AQI': str(aqi), 'Category': category,
            'Pollutant': row.get('ParameterName', 'AQI'), 'Area': area,
            'Observed': observed, 'Color': color, 'Status': 'EPA AirNow · Preliminary'}


def parse_contours(kml):
    root = ET.fromstring(kml)
    styles = {}
    for style in (element for element in root.iter() if element.tag.endswith('Style')):
        color = next((child.text for child in style.iter() if child.tag.endswith('color')), None)
        if color and len(color) == 8:
            styles['#' + style.attrib.get('id', '')] = (
                int(color[6:8], 16), int(color[4:6], 16), int(color[2:4], 16),
                min(170, int(color[0:2], 16)))
    contours = []
    for placemark in (element for element in root.iter() if element.tag.endswith('Placemark')):
        style_url = next((child.text for child in placemark if child.tag.endswith('styleUrl')), '')
        for coordinates in (element for element in placemark.iter()
                            if element.tag.endswith('coordinates')):
            points = []
            for value in coordinates.text.split():
                parts = value.split(',')
                if len(parts) < 2:
                    continue
                first, second = float(parts[0]), float(parts[1])
                # AirNow's EPSG:4326 KML currently uses latitude,longitude
                # axis order, although conventional KML uses longitude,latitude.
                if abs(first) <= 90 and abs(second) > 90:
                    first, second = second, first
                points.append((first, second))
            if len(points) >= 3:
                contours.append((styles.get(style_url, (128, 128, 128, 100)), points))
    return contours


class airnow:
    def __init__(self):
        self.app = App.get_running_app()
        self.data = empty_air_quality()

    def fetch(self, *args):
        key = self.app.config['Keys'].get('AirNow', '').strip()
        if not key:
            self.fail(None, 'AirNow API key missing')
            return
        latitude = float(self.app.config['Station']['Latitude'])
        longitude = float(self.app.config['Station']['Longitude'])
        query = urlencode({'format': 'text/csv', 'API_KEY': key,
                           'latitude': latitude, 'longitude': longitude})
        url = 'https://www.airnowapi.org/aq/observation/current/ziplatlong/?' + query
        UrlRequest(url, on_success=self.success, on_failure=self.fail,
                   on_error=self.fail, timeout=int(self.app.config['System']['Timeout']),
                   ca_file=certifi.where())

    def success(self, request, response):
        try:
            data = parse_airnow_csv(response)
            latitude = float(self.app.config['Station']['Latitude'])
            longitude = float(self.app.config['Station']['Longitude'])
            radius = int(self.app.config['AirNow']['Radius'])
            zoom = map_zoom(latitude, radius)
            tile_x, tile_y, marker_x, marker_y = map_tile(latitude, longitude, zoom)
            data['Map'] = self.data.get('Map', '')
            try:
                station_zone = ZoneInfo(self.app.config['Station']['Timezone'])
            except Exception:
                station_zone = datetime.now().astimezone().tzinfo
            data['Updated'] = datetime.now(station_zone).strftime('%H:%M')
            data['MarkerX'] = .5
            data['MarkerY'] = .5
            self.data = data
        except (TypeError, ValueError) as error:
            self.fail(None, str(error))
            return
        self.update_display()
        self.fetch_map(zoom, tile_x, tile_y, marker_x, marker_y)
        self.schedule()

    def fetch_map(self, zoom, tile_x, tile_y, marker_x, marker_y):
        os.makedirs('cache', exist_ok=True)
        hour = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime('%Y%m%d%H')
        path = ('cache/airnow-centered-v2-{}-{}-{}-{:03d}-{:03d}-{}.png'
                .format(zoom, tile_x, tile_y, round(marker_x * 1000),
                        round(marker_y * 1000), hour))
        if os.path.isfile(path):
            self.map_ready(path)
            return
        latitude = float(self.app.config['Station']['Latitude'])
        longitude = float(self.app.config['Station']['Longitude'])
        radius = int(self.app.config['AirNow']['Radius'])
        key = self.app.config['Keys']['AirNow'].strip()
        timeout = int(self.app.config['System']['Timeout'])
        worker = threading.Thread(
            target=self.build_centered_map,
            args=(path, zoom, tile_x, tile_y, marker_x, marker_y, latitude,
                  longitude, radius, key, timeout, hour), daemon=True)
        worker.start()

    def build_centered_map(self, path, zoom, tile_x, tile_y, marker_x,
                           marker_y, latitude, longitude, radius, key,
                           timeout, hour):
        """Download, composite and center the map without blocking Kivy's UI."""
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            mosaic = Image.new('RGBA', (768, 768))
            scale = 2 ** zoom
            headers = {'User-Agent': 'WeatherFlow-PiConsole/1.0'}
            for offset_y in range(-1, 2):
                for offset_x in range(-1, 2):
                    x = (tile_x + offset_x) % scale
                    y = max(0, min(scale - 1, tile_y + offset_y))
                    url = 'https://tile.openstreetmap.org/{}/{}/{}.png'.format(
                        zoom, x, y)
                    request = Request(url, headers=headers)
                    with urlopen(request, timeout=timeout, context=context) as response:
                        tile = Image.open(io.BytesIO(response.read())).convert('RGBA')
                    mosaic.paste(tile, ((offset_x + 1) * 256,
                                        (offset_y + 1) * 256))

            kml = None
            try:
                kml = self.download_contours(latitude, longitude, radius, key,
                                             timeout, hour, context)
                if not parse_contours(kml):
                    raise ValueError('AirNow returned no contour polygons')
                mosaic = self.add_contours(mosaic, kml, zoom, tile_x, tile_y)
            except Exception:
                if os.path.isfile('cache/airnow-last-good.png'):
                    Logger.info('AirNow: live contours unavailable; using last map')
                else:
                    Logger.warning('AirNow: contours unavailable; retry scheduled')
                Clock.schedule_once(
                    lambda _dt: self.map_retry(zoom, tile_x, tile_y, marker_x,
                                               marker_y), 0)
                return

            image = mosaic.crop(centered_crop(marker_x, marker_y))
            image.save(path)
            image.save('cache/airnow-last-good.png')
            Clock.schedule_once(lambda _dt: self.map_ready(path), 0)
        except Exception:
            Logger.warning('AirNow: unable to update centered local map')

    @staticmethod
    def download_contours(latitude, longitude, radius, key, timeout, hour,
                          context):
        latitude_delta = radius / 69.0
        longitude_delta = radius / (69.0 * math.cos(math.radians(latitude)))
        bbox = '{},{},{},{}'.format(longitude-longitude_delta, latitude-latitude_delta,
                                    longitude+longitude_delta, latitude+latitude_delta)
        query = urlencode({'date': datetime.strptime(hour, '%Y%m%d%H').strftime('%Y-%m-%dT%H'),
                           'bbox': bbox, 'srs': 'EPSG:4326',
                           'API_KEY': key})
        url = 'https://www.airnowapi.org/aq/kml/combined/?' + query
        request = Request(url, headers={'User-Agent': 'WeatherFlow-PiConsole/1.0'})
        with urlopen(request, timeout=timeout, context=context) as response:
            return response.read()

    @staticmethod
    def add_contours(image, kml, zoom, tile_x, tile_y):
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        drawing = ImageDraw.Draw(overlay)
        scale = 2 ** zoom
        for color, coordinates in parse_contours(kml):
            pixels = []
            for longitude, latitude in coordinates:
                x = (((longitude + 180.0) / 360.0 * scale) -
                     (tile_x - 1)) * 256
                latitude_rad = math.radians(latitude)
                y = (((1.0 - math.asinh(math.tan(latitude_rad)) / math.pi) /
                     2.0 * scale) - (tile_y - 1)) * 256
                pixels.append((x, y))
            drawing.polygon(pixels, fill=color)
        return Image.alpha_composite(image, overlay)

    def map_ready(self, path):
        if hasattr(self.app.Sched, 'airnow_map_retry'):
            self.app.Sched.airnow_map_retry.cancel()
        self.data['Map'] = path
        self.update_display()

    def map_retry(self, zoom, tile_x, tile_y, marker_x, marker_y):
        """Keep the last contour map visible and retry transient API failures."""
        fallback = 'cache/airnow-last-good.png'
        if os.path.isfile(fallback):
            self.data['Map'] = fallback
            self.update_display()
        if hasattr(self.app.Sched, 'airnow_map_retry'):
            self.app.Sched.airnow_map_retry.cancel()
        self.app.Sched.airnow_map_retry = Clock.schedule_once(
            lambda _dt: self.fetch_map(zoom, tile_x, tile_y, marker_x, marker_y),
            5 * 60)

    def map_fail(self, *args):
        Logger.warning('AirNow: unable to update local map tile')

    def fail(self, request, error):
        Logger.warning('AirNow: unable to update air-quality observation')
        if self.data.get('AQI', '--') == '--':
            self.data = empty_air_quality('AirNow update unavailable')
        else:
            self.data = dict(self.data)
            self.data['Status'] = 'AirNow update unavailable · showing last reading'
        self.update_display()
        self.schedule(5)

    def update_display(self):
        self.app.CurrentConditions.AirQuality = dict(self.data)

    def schedule(self, minutes=None):
        if hasattr(self.app.Sched, 'airnow'):
            self.app.Sched.airnow.cancel()
        interval = minutes or int(self.app.config['AirNow']['RefreshInterval'])
        self.app.Sched.airnow = Clock.schedule_once(self.fetch, interval * 60)
