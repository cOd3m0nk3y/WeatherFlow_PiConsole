"""Normalize WeatherFlow daily forecasts for the extended forecast panel."""

from datetime import datetime, timezone as utc_timezone
from zoneinfo import ZoneInfo

WEATHER_ICONS = {
    'clear-day', 'clear-night', 'rainy', 'possibly-rainy-day',
    'possibly-rainy-night', 'snow', 'possibly-snow-day',
    'possibly-snow-night', 'sleet', 'possibly-sleet-day',
    'possibly-sleet-night', 'thunderstorm',
    'possibly-thunderstorm-day', 'possibly-thunderstorm-night', 'windy',
    'foggy', 'cloudy', 'partly-cloudy-day', 'partly-cloudy-night'
}


def empty_day():
    """Return one display-safe placeholder day."""

    return {'day': '--', 'date': '--', 'conditions': 'Unavailable', 'icon': '-',
            'high': '--', 'low': '--', 'precip': '--'}


def empty_days(count=10):
    """Return independent placeholder dictionaries for the panel."""

    return [empty_day() for _ in range(count)]


def _temperature(value, unit):
    unit = unit.strip().lower()
    if value is None:
        display = '-'
    else:
        if unit == 'f':
            value = value * (9 / 5) + 32
        display = '{:.0f}'.format(abs(value) if round(value, 1) == 0 else value)
    suffix = '\N{DEGREE FAHRENHEIT}' if unit == 'f' else '\N{DEGREE CELSIUS}'
    return display + suffix


def normalize_daily_forecast(daily_forecasts, timezone, temp_unit, count=10):
    """Convert WeatherFlow daily records into compact, display-ready values."""

    zone = ZoneInfo(timezone)
    normalized = []
    for index, daily in enumerate(daily_forecasts[:count]):
        timestamp = daily.get('day_start_local')
        if timestamp is not None:
            local_date = datetime.fromtimestamp(timestamp, utc_timezone.utc).astimezone(zone)
            if index == 0:
                day = 'Today'
            elif index == 1:
                day = 'Tomorrow'
            else:
                day = local_date.strftime('%a')
            date = '{} {}'.format(local_date.strftime('%b'), local_date.day)
        else:
            day = ('Today' if index == 0 else
                   'Tomorrow' if index == 1 else 'Day {}'.format(index + 1))
            date = '--'

        icon = daily.get('icon', '-')
        normalized.append({
            'day': day,
            'date': date,
            'conditions': daily.get('conditions', 'Unavailable').capitalize(),
            'icon': icon if icon in WEATHER_ICONS else '-',
            'high': _temperature(daily.get('air_temp_high'), temp_unit),
            'low': _temperature(daily.get('air_temp_low'), temp_unit),
            'precip': '{}%'.format(round(daily.get('precip_probability') or 0))
        })

    normalized.extend(empty_days(count - len(normalized)))
    return normalized
