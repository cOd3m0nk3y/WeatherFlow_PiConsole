"""Centered National Weather Service radar map for PiConsole."""

import io
import json
import os
import ssl
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
from PIL import Image
from kivy.app import App
from kivy.clock import Clock
from kivy.logger import Logger

from lib.map_utils import centered_crop, map_tile, map_zoom


WMS_URL = 'https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows'
TIME_SERVICE_URL = ('https://mapservices.weather.noaa.gov/eventdriven/rest/'
                    'services/radar/radar_base_reflectivity_time/ImageServer')
MIN_RADAR_COVERAGE = .1
RADAR_EDGE_MARGIN = 12
HOUSE_MARKER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 'icons', 'radar', 'house-marker-v2.png')


def empty_radar(status='Loading NWS radar'):
    return {'Map': '', 'Updated': '--', 'Status': status, 'Radius': '--',
            'Coverage': '--', 'Label': 'Loading'}


def mercator_mosaic_bbox(zoom, tile_x, tile_y):
    """EPSG:3857 bounds for the 3x3 tile mosaic around tile_x/tile_y."""
    extent = 20037508.342789244
    span = extent * 2 / (2 ** zoom)
    left = -extent + (tile_x - 1) * span
    right = -extent + (tile_x + 2) * span
    top = extent - (tile_y - 1) * span
    bottom = extent - (tile_y + 2) * span
    return left, bottom, right, top


def radar_wms_url(zoom, tile_x, tile_y, size=768):
    bbox = ','.join('{:.3f}'.format(value) for value in
                    mercator_mosaic_bbox(zoom, tile_x, tile_y))
    query = urlencode({'service': 'WMS', 'version': '1.1.1',
                       'request': 'GetMap', 'layers': 'conus_bref_qcd',
                       'styles': '', 'srs': 'EPSG:3857', 'bbox': bbox,
                       'width': size, 'height': size, 'format': 'image/png',
                       'transparent': 'true'})
    return WMS_URL + '?' + query


def radar_catalog_url(zoom, tile_x, tile_y):
    bbox = ','.join('{:.3f}'.format(value) for value in
                    mercator_mosaic_bbox(zoom, tile_x, tile_y))
    query = urlencode({'where': '1=1', 'outFields': 'idp_validtime',
                       'returnGeometry': 'false',
                       'orderByFields': 'idp_validtime DESC',
                       'resultRecordCount': 100, 'geometry': bbox,
                       'geometryType': 'esriGeometryEnvelope', 'inSR': 3857,
                       'spatialRel': 'esriSpatialRelIntersects', 'f': 'json'})
    return TIME_SERVICE_URL + '/query?' + query


def radar_frame_url(zoom, tile_x, tile_y, timestamp, size=768):
    bbox = ','.join('{:.3f}'.format(value) for value in
                    mercator_mosaic_bbox(zoom, tile_x, tile_y))
    query = urlencode({'bbox': bbox, 'bboxSR': 3857,
                       'size': '{},{}'.format(size, size), 'imageSR': 3857,
                       'format': 'png32', 'transparent': 'true',
                       'time': timestamp, 'f': 'image'})
    return TIME_SERVICE_URL + '/exportImage?' + query


def select_hour_frames(catalog):
    """Select distinct published frames spanning the service's latest hour."""
    timestamps = sorted({int(feature['attributes']['idp_validtime'])
                         for feature in catalog.get('features', [])
                         if feature.get('attributes', {}).get('idp_validtime')},
                        reverse=True)
    if not timestamps:
        return []
    latest = timestamps[0]
    selected = []
    for timestamp in timestamps:
        if timestamp < latest - 60 * 60 * 1000:
            continue
        if not selected or selected[-1] - timestamp >= 4 * 60 * 1000:
            selected.append(timestamp)
    return list(reversed(selected))


def radar_status(overlay, crop_box):
    """Describe whether the station-centered portion contains radar echoes."""
    local_overlay = overlay.crop(crop_box)
    local_alpha = local_overlay.getchannel('A').crop(
        (RADAR_EDGE_MARGIN, RADAR_EDGE_MARGIN,
         local_overlay.width - RADAR_EDGE_MARGIN,
         local_overlay.height - RADAR_EDGE_MARGIN))
    visible_pixels = sum(local_alpha.histogram()[16:])
    coverage = visible_pixels / (local_alpha.width * local_alpha.height) * 100
    return ('NWS base reflectivity' if coverage >= MIN_RADAR_COVERAGE
            else 'No precipitation detected')


def precipitation_coverage(overlay, crop_box):
    """Return formatted radar-echo coverage for the displayed map area."""
    alpha = overlay.crop(crop_box).getchannel('A')
    echo_pixels = sum(alpha.histogram()[16:])
    percentage = echo_pixels / (alpha.width * alpha.height) * 100
    if percentage == 0:
        return '0%'
    if percentage < .1:
        return '<0.1%'
    if percentage < 10:
        return '{:.1f}%'.format(percentage)
    return '{:.0f}%'.format(percentage)


def expanded_radius(configured_radius, configured_zoom, selected_zoom):
    """Approximate displayed radius after stepping out through slippy zooms."""
    return configured_radius * (2 ** (configured_zoom - selected_zoom))


def zoom_levels(configured_zoom, zoom_out_limit, minimum_zoom=3):
    """Return candidate zooms; a zero limit means search until echoes appear."""
    last_zoom = (minimum_zoom if zoom_out_limit == 0 else
                 max(minimum_zoom, configured_zoom - zoom_out_limit))
    return range(configured_zoom, last_zoom - 1, -1)


def draw_house_marker(image):
    """Composite the generated station marker at the map center."""
    with Image.open(HOUSE_MARKER_PATH) as source:
        marker = source.convert('RGBA')
    position = ((image.width - marker.width) // 2,
                (image.height - marker.height) // 2)
    image.alpha_composite(marker, position)
    return image


class radar:
    def __init__(self):
        self.app = App.get_running_app()
        self.data = empty_radar()
        self.frames = []
        self.frame_index = 0

    def fetch(self, *args):
        try:
            latitude = float(self.app.config['Station']['Latitude'])
            longitude = float(self.app.config['Station']['Longitude'])
            radius = int(self.app.config['Radar']['Radius'])
            zoom_out_limit = int(self.app.config['Radar']['ZoomOutLimit'])
            animation = int(self.app.config['Radar']['Animation'])
            zoom = map_zoom(latitude, radius)
            tile_x, tile_y, marker_x, marker_y = map_tile(
                latitude, longitude, zoom)
            timeout = int(self.app.config['System']['Timeout'])
        except (KeyError, TypeError, ValueError):
            self.fail('Invalid radar configuration')
            return

        interval = int(self.app.config['Radar']['RefreshInterval'])
        minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        minute = minute.replace(minute=minute.minute - minute.minute % interval)
        stamp = minute.strftime('%Y%m%d%H%M')
        os.makedirs('cache', exist_ok=True)
        path = ('cache/radar-centered-v15-{}-{}-{}-{:03d}-{:03d}-limit{}-anim{}-{}.png'
                .format(zoom, tile_x, tile_y, round(marker_x * 1000),
                        round(marker_y * 1000), zoom_out_limit, animation,
                        stamp))
        if os.path.isfile(path):
            status = 'NWS base reflectivity'
            display_radius = radius
            coverage = '--'
            frames = []
            try:
                with open(path + '.status', encoding='utf-8') as status_file:
                    metadata = status_file.read().splitlines()
                    status = metadata[0].strip() or status
                    if len(metadata) > 1:
                        display_radius = int(metadata[1])
                    if len(metadata) > 2:
                        coverage = metadata[2].strip() or coverage
                    for frame in metadata[3:]:
                        frame_path, timestamp, frame_coverage = frame.split('|')
                        if os.path.isfile(frame_path):
                            frames.append((frame_path, int(timestamp),
                                           frame_coverage))
            except (OSError, ValueError):
                pass
            self.ready(path, minute, status, display_radius, coverage, frames)
            self.schedule()
            return

        threading.Thread(target=self.build_map,
                         args=(path, minute, zoom, tile_x, tile_y, marker_x,
                               marker_y, radius, zoom_out_limit, animation,
                               timeout),
                         daemon=True).start()
        self.schedule()

    def build_map(self, path, updated, zoom, tile_x, tile_y, marker_x,
                  marker_y, configured_radius, zoom_out_limit, animation,
                  timeout):
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            headers = {'User-Agent': 'WeatherFlow-PiConsole/1.0'}
            selected_zoom = zoom
            selected_tile_x, selected_tile_y = tile_x, tile_y
            selected_marker_x, selected_marker_y = marker_x, marker_y
            overlay = None

            # Prefer the configured radius. If it is clear, progressively zoom
            # out until the closest visible radar echo is included.
            latitude = float(self.app.config['Station']['Latitude'])
            longitude = float(self.app.config['Station']['Longitude'])
            status = 'No precipitation detected'
            for candidate_zoom in zoom_levels(zoom, zoom_out_limit):
                candidate_x, candidate_y, candidate_fx, candidate_fy = map_tile(
                    latitude, longitude, candidate_zoom)
                with urlopen(Request(radar_wms_url(candidate_zoom, candidate_x,
                                                   candidate_y), headers=headers),
                             timeout=timeout, context=context) as response:
                    candidate_overlay = Image.open(
                        io.BytesIO(response.read())).convert('RGBA')
                candidate_crop = centered_crop(candidate_fx, candidate_fy)
                status = radar_status(candidate_overlay, candidate_crop)
                selected_zoom = candidate_zoom
                selected_tile_x, selected_tile_y = candidate_x, candidate_y
                selected_marker_x, selected_marker_y = candidate_fx, candidate_fy
                overlay = candidate_overlay
                if status == 'NWS base reflectivity':
                    break

            mosaic = Image.new('RGBA', (768, 768))
            scale = 2 ** selected_zoom
            for offset_y in range(-1, 2):
                for offset_x in range(-1, 2):
                    x = (selected_tile_x + offset_x) % scale
                    y = max(0, min(scale - 1, selected_tile_y + offset_y))
                    url = 'https://tile.openstreetmap.org/{}/{}/{}.png'.format(
                        selected_zoom, x, y)
                    with urlopen(Request(url, headers=headers), timeout=timeout,
                                 context=context) as response:
                        tile = Image.open(io.BytesIO(response.read())).convert('RGBA')
                    mosaic.paste(tile, ((offset_x + 1) * 256,
                                        (offset_y + 1) * 256))

            crop_box = centered_crop(selected_marker_x, selected_marker_y)
            display_radius = expanded_radius(configured_radius, zoom, selected_zoom)
            if status == 'NWS base reflectivity' and selected_zoom < zoom:
                status = 'Precipitation in expanded view'

            overlays = [(int(updated.timestamp() * 1000), overlay)]
            if animation:
                try:
                    with urlopen(Request(radar_catalog_url(
                            selected_zoom, selected_tile_x, selected_tile_y),
                            headers=headers), timeout=timeout,
                            context=context) as response:
                        timestamps = select_hour_frames(json.loads(
                            response.read().decode('utf-8')))
                    historical = []
                    for timestamp in timestamps:
                        with urlopen(Request(radar_frame_url(
                                selected_zoom, selected_tile_x, selected_tile_y,
                                timestamp), headers=headers), timeout=timeout,
                                context=context) as response:
                            frame_overlay = Image.open(
                                io.BytesIO(response.read())).convert('RGBA')
                        historical.append((timestamp, frame_overlay))
                    if historical:
                        overlays = historical
                except Exception:
                    Logger.warning('Radar: animation history unavailable; using latest frame')

            frames = []
            for index, (timestamp, frame_overlay) in enumerate(overlays):
                frame_coverage = precipitation_coverage(frame_overlay, crop_box)
                image = Image.alpha_composite(mosaic, frame_overlay).crop(crop_box)
                draw_house_marker(image)
                frame_path = (path if index == len(overlays) - 1 else
                              path[:-4] + '-frame-{}.png'.format(timestamp))
                image.save(frame_path)
                frames.append((frame_path, timestamp, frame_coverage))
            coverage = frames[-1][2]
            with open(path + '.status', 'w', encoding='utf-8') as status_file:
                metadata = ['{}\n{}\n{}'.format(status, display_radius, coverage)]
                metadata.extend('{}|{}|{}'.format(*frame) for frame in frames)
                status_file.write('\n'.join(metadata))
            Clock.schedule_once(
                lambda _dt: self.ready(path, updated, status, display_radius,
                                       coverage, frames), 0)
        except Exception:
            Logger.warning('Radar: unable to update NWS radar map')
            Clock.schedule_once(lambda _dt: self.fail('NWS radar unavailable'), 0)

    def ready(self, path, updated, status='NWS base reflectivity', radius='--',
              coverage='--', frames=None):
        if hasattr(self.app.Sched, 'radar_animation'):
            self.app.Sched.radar_animation.cancel()
        label = ('Expanded' if status == 'Precipitation in expanded view' else
                 'Clear' if status == 'No precipitation detected' else 'Local')
        self.frames = frames or []
        self.frame_index = 0
        if len(self.frames) > 1:
            label = 'Loop'
            path, timestamp, coverage = self.frames[0]
            updated_text = self.format_frame_time(timestamp)
        else:
            updated_text = updated.astimezone().strftime('%H:%M')
        self.data = {'Map': path, 'Updated': updated.astimezone().strftime('%H:%M'),
                     'Status': status, 'Radius': str(radius),
                     'Coverage': coverage, 'Label': label}
        self.data['Updated'] = updated_text
        self.update_display()
        if len(self.frames) > 1:
            self.app.Sched.radar_animation = Clock.schedule_interval(
                self.animate_frame, 1.25)

    @staticmethod
    def format_frame_time(timestamp):
        return datetime.fromtimestamp(
            timestamp / 1000, timezone.utc).astimezone().strftime('%H:%M')

    def animate_frame(self, *args):
        if not self.frames:
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        path, timestamp, coverage = self.frames[self.frame_index]
        self.data = dict(self.data)
        self.data['Map'] = path
        self.data['Updated'] = self.format_frame_time(timestamp)
        self.data['Coverage'] = coverage
        self.update_display()

    def fail(self, status):
        self.data = {'Map': self.data.get('Map', ''),
                     'Updated': self.data.get('Updated', '--'), 'Status': status,
                     'Radius': self.data.get('Radius', '--'),
                     'Coverage': self.data.get('Coverage', '--'),
                     'Label': 'Unavailable'}
        self.update_display()

    def update_display(self):
        self.app.CurrentConditions.Radar = dict(self.data)

    def schedule(self):
        if hasattr(self.app.Sched, 'radar'):
            self.app.Sched.radar.cancel()
        interval = int(self.app.config['Radar']['RefreshInterval'])
        self.app.Sched.radar = Clock.schedule_once(self.fetch, interval * 60)
