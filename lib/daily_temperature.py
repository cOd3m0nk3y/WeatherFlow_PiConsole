"""Daily actual and forecast temperature series for PiConsole."""

from datetime import datetime
import json
import os

import pytz
from kivy.app import App
from kivy.clock import mainthread
from kivy.logger import Logger

from lib import properties


def convert_temperature(value, unit):
    """Convert a Celsius value to the configured display unit."""

    if value is None:
        return None
    return value * 9 / 5 + 32 if unit.lower() == 'f' else value


def local_hour(timestamp, timezone):
    """Return fractional local hour for a UNIX timestamp."""

    local = datetime.fromtimestamp(timestamp, pytz.utc).astimezone(timezone)
    return local.hour + local.minute / 60 + local.second / 3600


def forecast_series(hourly, day, timezone):
    """Extract one local calendar day's hourly Celsius forecast series."""

    points = []
    for item in hourly or []:
        timestamp = item.get('time')
        temperature = item.get('air_temperature')
        if timestamp is None or temperature is None:
            continue
        local = datetime.fromtimestamp(timestamp, pytz.utc).astimezone(timezone)
        if local.date() == day:
            points.append([local_hour(timestamp, timezone), float(temperature)])
    return sorted(points)


def observation_series(observations, day, timezone, temperature_index):
    """Extract one local day's temperature values from WeatherFlow buckets."""

    points = []
    for item in observations or []:
        try:
            timestamp = int(item[0])
            temperature = item[temperature_index]
        except (IndexError, TypeError, ValueError):
            continue
        if temperature is None:
            continue
        local = datetime.fromtimestamp(timestamp, pytz.utc).astimezone(timezone)
        if local.date() == day:
            points.append([timestamp, float(temperature)])
    return sorted(points)


def series_until(points, cutoff):
    """Return a series through cutoff, interpolating or extending its end."""

    if not points:
        return []
    result = [list(point) for point in points if point[0] <= cutoff]
    future = next((point for point in points if point[0] > cutoff), None)
    if result and result[-1][0] < cutoff:
        previous = result[-1]
        if future is None:
            result.append([cutoff, previous[1]])
        else:
            span = future[0] - previous[0]
            fraction = (cutoff - previous[0]) / span if span else 0
            value = previous[1] + fraction * (future[1] - previous[1])
            result.append([cutoff, value])
    return result


def series_from(points, cutoff):
    """Return a series from cutoff, using forecast values at the boundary."""

    if not points:
        return []
    future = [list(point) for point in points if point[0] >= cutoff]
    previous = next((point for point in reversed(points) if point[0] < cutoff), None)
    if future and future[0][0] > cutoff:
        if previous is None:
            value = future[0][1]
        else:
            span = future[0][0] - previous[0]
            fraction = (cutoff - previous[0]) / span if span else 0
            value = previous[1] + fraction * (future[0][1] - previous[1])
        future.insert(0, [cutoff, value])
    return future


class daily_temperature:
    """Maintain daily observations, forecast snapshots, and display values."""

    def __init__(self):
        self.app = App.get_running_app()
        self.timezone = pytz.timezone(self.app.config['Station']['Timezone'])
        self.day = self._now().date()
        self.actual = []
        self.baseline = []
        self.baseline_label = 'Baseline'
        self.current_forecast = []
        self.cache_path = os.path.join('cache', 'daily-temperature-forecast.json')
        self._load_baseline()

    def _now(self):
        return datetime.now(pytz.utc).astimezone(self.timezone)

    def _ensure_day(self):
        today = self._now().date()
        if today == self.day:
            return
        self.day = today
        self.actual = []
        self.baseline = []
        self.baseline_label = 'Baseline'
        self.current_forecast = []
        self._load_baseline()

    def _load_baseline(self):
        try:
            with open(self.cache_path, encoding='utf-8') as cache_file:
                cached = json.load(cache_file)
            if cached.get('date') == self.day.isoformat():
                self.baseline = cached.get('forecast', [])
                self.baseline_label = cached.get('label', 'Baseline')
        except (OSError, ValueError, TypeError):
            return

    def _save_baseline(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as cache_file:
                json.dump({'date': self.day.isoformat(),
                           'forecast': self.baseline,
                           'label': self.baseline_label}, cache_file)
        except OSError:
            Logger.warning('DailyTemperature: unable to save forecast baseline')

    @mainthread
    def ingest_history(self, response, temperature_index):
        """Reuse the parser's existing WeatherFlow `today` API response."""

        if response is None:
            return
        try:
            payload = response.json() if hasattr(response, 'json') else response
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        self._ensure_day()
        history = observation_series(payload.get('obs', []), self.day,
                                     self.timezone, temperature_index)
        known = {point[0]: point for point in self.actual}
        known.update({point[0]: point for point in history})
        self.actual = sorted(known.values())
        self.update_display()

    def update_forecast(self, response):
        """Retain the day's first forecast and track the latest forecast."""

        self._ensure_day()
        hourly = response.get('forecast', {}).get('hourly', [])
        latest = forecast_series(hourly, self.day, self.timezone)
        if not latest:
            return
        self.current_forecast = latest
        if not self.baseline:
            self.baseline = list(latest)
            self.baseline_label = ('Midnight' if local_hour(
                self._now().timestamp(), self.timezone) <= 1.5 else 'Startup')
            self._save_baseline()
        self.update_display()

    def observe(self, timestamp, temperature):
        """Append a live outdoor temperature observation."""

        if timestamp is None or temperature is None:
            return
        self._ensure_day()
        local = datetime.fromtimestamp(timestamp, pytz.utc).astimezone(self.timezone)
        if local.date() != self.day:
            return
        point = [int(timestamp), float(temperature)]
        if self.actual and self.actual[-1][0] == point[0]:
            self.actual[-1] = point
        else:
            self.actual.append(point)
        self.update_display()

    @mainthread
    def update_display(self):
        unit = self.app.config['Units']['Temp'].lower()
        now_hour = local_hour(self._now().timestamp(), self.timezone)

        def display(points, timestamps=False):
            return [[local_hour(x, self.timezone) if timestamps else x,
                     convert_temperature(y, unit)] for x, y in points]

        actual = display(self.actual, timestamps=True)
        baseline = display(series_until(self.baseline, now_hour))
        actual_values = [point[1] for point in actual]
        forecast_values = [convert_temperature(point[1], unit)
                           for point in self.baseline]
        current_value = actual_values[-1] if actual_values else None
        current = display(series_from(self.current_forecast, now_hour))
        suffix = '\N{DEGREE FAHRENHEIT}' if unit == 'f' else '\N{DEGREE CELSIUS}'

        def high_low(values):
            if not values:
                return '-- / --'
            return '{:.0f} / {:.0f}{}'.format(max(values), min(values), suffix)

        data = properties.DailyTemperature()
        data.update({
            'Actual': actual,
            'Baseline': baseline,
            'CurrentForecast': current,
            'NowHour': now_hour,
            'Current': '--' if current_value is None else
                       '{:.1f}{}'.format(current_value, suffix),
            'ActualHighLow': high_low(actual_values),
            'ForecastHighLow': high_low(forecast_values),
            'BaselineLabel': self.baseline_label,
            'Status': 'Actual · midnight forecast · latest forecast',
        })
        try:
            self.app.CurrentConditions.DailyTemperature = data
        except ReferenceError:
            Logger.warning('DailyTemperature: ignored stale panel binding')

    def reformat(self):
        self.update_display()
