"""AirNow observations and map state for PiConsole."""

import csv
import io
import math
import os
import ssl
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from lib.time_format import format_clock

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
            'Status': status, 'Map': '', 'MapStatus': 'Loading map',
            'MarkerX': .5, 'MarkerY': .5}


def contour_hours(now):
    """Return at most two likely-published AirNow contour hours."""
    age = 2 if now.minute < 30 else 1
    hours = [now - timedelta(hours=age)]
    if age == 1:
        hours.append(now - timedelta(hours=2))
    return [value.strftime('%Y%m%d%H') for value in hours]


def is_rate_limited(request=None, error=None):
    """Recognize Kivy and urllib forms of an AirNow HTTP 429 response."""
    status = getattr(request, 'resp_status', None)
    return (status == 429 or getattr(error, 'code', None) == 429 or
            'request limit exceeded' in str(error).lower())


def area_tint(image, color):
    """Apply a reporting-area AQI tint when spatial contours are unavailable."""
    try:
        red, green, blue = (int(color[index:index + 2], 16)
                            for index in (0, 2, 4))
    except (TypeError, ValueError):
        red, green, blue = 128, 128, 128
    overlay = Image.new('RGBA', image.size, (red, green, blue, 72))
    return Image.alpha_composite(image, overlay)


def refresh_minutes(configured):
    """Protect shared AirNow API keys from overly frequent polling."""
    return max(60, int(configured))


def preserve_map_state(data, previous):
    """Carry map fields across an independently refreshed observation."""
    data['Map'] = previous.get('Map', '')
    data['MapStatus'] = previous.get('MapStatus', 'Loading map')
    data['MarkerX'] = .5
    data['MarkerY'] = .5
    return data


def format_observed(row, time_format='24 hr'):
    date = str(row.get('DateObserved', '')).strip()
    try:
        date = datetime.strptime(date, '%Y-%m-%d').strftime('%b %d')
    except ValueError:
        pass
    raw_hour = str(row.get('HourObserved', '')).strip()
    try:
        if ':' in raw_hour:
            observed_time = datetime.strptime(
                raw_hour, '%H:%M:%S' if raw_hour.count(':') == 2 else '%H:%M')
        else:
            observed_time = datetime(2000, 1, 1, int(float(raw_hour)))
        hour = format_clock(observed_time, time_format)
    except ValueError:
        hour = raw_hour
    zone = str(row.get('LocalTimeZone', '')).strip()
    return ' '.join(value for value in (date, hour, zone) if value) or '--'


def parse_airnow_csv(text, time_format='24 hr'):
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
    observed = format_observed(row, time_format)
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
            time_format = self.app.config['Display']['TimeFormat']
            data = parse_airnow_csv(response, time_format)
            latitude = float(self.app.config['Station']['Latitude'])
            longitude = float(self.app.config['Station']['Longitude'])
            radius = int(self.app.config['AirNow']['Radius'])
            zoom = map_zoom(latitude, radius)
            tile_x, tile_y, marker_x, marker_y = map_tile(latitude, longitude, zoom)
            preserve_map_state(data, self.data)
            try:
                station_zone = ZoneInfo(self.app.config['Station']['Timezone'])
            except Exception:
                station_zone = datetime.now().astimezone().tzinfo
            data['Updated'] = format_clock(datetime.now(station_zone),
                                           time_format)
            self.data = data
        except (TypeError, ValueError) as error:
            self.fail(None, str(error))
            return
        self.update_display()
        self.fetch_map(zoom, tile_x, tile_y, marker_x, marker_y)
        self.schedule()

    def fetch_map(self, zoom, tile_x, tile_y, marker_x, marker_y):
        os.makedirs('cache', exist_ok=True)
        hours = contour_hours(datetime.now(timezone.utc))
        path = ('cache/airnow-centered-v3-{}-{}-{}-{:03d}-{:03d}-{}.png'
                .format(zoom, tile_x, tile_y, round(marker_x * 1000),
                        round(marker_y * 1000), hours[0]))
        if os.path.isfile(path):
            map_status, panel_status = 'AirNow map · cached', None
            try:
                with open(path + '.status', encoding='utf-8') as status_file:
                    values = status_file.read().splitlines()
                map_status = values[0]
                panel_status = values[1] if len(values) > 1 else None
            except OSError:
                pass
            self.map_ready(path, map_status, panel_status)
            return
        latitude = float(self.app.config['Station']['Latitude'])
        longitude = float(self.app.config['Station']['Longitude'])
        radius = int(self.app.config['AirNow']['Radius'])
        key = self.app.config['Keys']['AirNow'].strip()
        timeout = int(self.app.config['System']['Timeout'])
        worker = threading.Thread(
            target=self.build_centered_map,
            args=(path, zoom, tile_x, tile_y, marker_x, marker_y, latitude,
                  longitude, radius, key, timeout, hours,
                  self.data.get('Color', '808080ff')), daemon=True)
        worker.start()

    def build_centered_map(self, path, zoom, tile_x, tile_y, marker_x,
                           marker_y, latitude, longitude, radius, key,
                           timeout, hours, color):
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
            rate_limited = False
            for hour in hours:
                try:
                    candidate = self.download_contours(
                        latitude, longitude, radius, key, timeout, hour, context)
                    if parse_contours(candidate):
                        kml = candidate
                        break
                except HTTPError as error:
                    if is_rate_limited(error=error):
                        rate_limited = True
                        break
                except Exception:
                    continue

            if kml:
                mosaic = self.add_contours(mosaic, kml, zoom, tile_x, tile_y)
                map_status = 'AirNow contours'
                panel_status = 'EPA AirNow · Preliminary'
            else:
                mosaic = area_tint(mosaic, color)
                map_status = ('Area AQI tint · API limit' if rate_limited else
                              'Area AQI tint · contours unavailable')
                panel_status = ('API Key Limit Exceeded' if rate_limited else
                                'Contours unavailable · area AQI shown')
                Logger.warning('AirNow: {}; using area AQI tint'.format(
                    'API request limit exceeded' if rate_limited else
                    'contours unavailable'))

            image = mosaic.crop(centered_crop(marker_x, marker_y))
            image.save(path)
            with open(path + '.status', 'w', encoding='utf-8') as status_file:
                status_file.write(map_status + '\n' + panel_status)
            Clock.schedule_once(
                lambda _dt: self.map_ready(path, map_status, panel_status), 0)
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

    def map_ready(self, path, map_status='AirNow contours', panel_status=None):
        if hasattr(self.app.Sched, 'airnow_map_retry'):
            self.app.Sched.airnow_map_retry.cancel()
        self.data['Map'] = path
        self.data['MapStatus'] = map_status
        if panel_status:
            self.data['Status'] = panel_status
        self.update_display()

    def map_fail(self, *args):
        Logger.warning('AirNow: unable to update local map tile')

    def fail(self, request, error):
        Logger.warning('AirNow: unable to update air-quality observation')
        rate_limited = is_rate_limited(request, error)
        if self.data.get('AQI', '--') == '--':
            self.data = empty_air_quality(
                'API Key Limit Exceeded' if rate_limited else
                'AirNow update unavailable')
        else:
            self.data = dict(self.data)
            self.data['Status'] = (
                'API Key Limit Exceeded · stale reading' if rate_limited else
                'AirNow unavailable · stale reading')
        self.update_display()
        self.schedule()

    def update_display(self):
        self.app.CurrentConditions.AirQuality = dict(self.data)

    def schedule(self, minutes=None):
        if hasattr(self.app.Sched, 'airnow'):
            self.app.Sched.airnow.cancel()
        interval = refresh_minutes(
            minutes or self.app.config['AirNow']['RefreshInterval'])
        self.app.Sched.airnow = Clock.schedule_once(self.fetch, interval * 60)
