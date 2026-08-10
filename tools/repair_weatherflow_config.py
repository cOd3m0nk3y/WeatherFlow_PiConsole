"""Fill missing WeatherFlow station/device metadata in wfpiconsole.ini."""

import argparse
import configparser
import os
import sys
import tempfile

import requests


DEVICE_FIELDS = {
    'ST': ('TempestID', 'TempestSN', 'TempestHeight'),
    'SK': ('SkyID', 'SkySN', 'SkyHeight'),
}


def metadata_updates(config, payload):
    """Return blank INI fields that can be safely derived from API metadata."""

    station_id = int(config['Station']['StationID'])
    station = next((item for item in payload.get('stations', [])
                    if item.get('station_id') == station_id), None)
    if station is None:
        raise ValueError('Configured station was not returned by WeatherFlow')

    updates = {}
    station_fields = {
        'Latitude': station.get('latitude'),
        'Longitude': station.get('longitude'),
        'Timezone': station.get('timezone'),
        'Elevation': station.get('station_meta', {}).get('elevation'),
        'Name': station.get('name'),
    }
    for key, value in station_fields.items():
        if not config['Station'].get(key, '').strip() and value is not None:
            updates[key] = value

    for device in station.get('devices', []):
        fields = DEVICE_FIELDS.get(device.get('device_type'))
        if fields is None:
            continue
        id_key, serial_key, height_key = fields
        configured_id = config['Station'].get(id_key, '').strip()
        if configured_id and configured_id != str(device.get('device_id')):
            continue
        if not configured_id and device.get('device_id') is not None:
            updates[id_key] = device['device_id']
        if not config['Station'].get(serial_key, '').strip() and device.get('serial_number'):
            updates[serial_key] = device['serial_number']
        height = device.get('device_meta', {}).get('agl')
        if not config['Station'].get(height_key, '').strip() and height is not None:
            updates[height_key] = height

    return updates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='wfpiconsole.ini')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.optionxform = str
    if not config.read(args.config):
        sys.exit('Configuration file not found: {}'.format(args.config))
    token = config.get('Keys', 'WeatherFlow', fallback='').strip()
    station_id = config.get('Station', 'StationID', fallback='').strip()
    if not token or not station_id:
        sys.exit('WeatherFlow token and StationID must be set first')

    try:
        response = requests.get(
            'https://swd.weatherflow.com/swd/rest/stations/',
            params={'token': token}, timeout=20)
        if response.status_code != 200:
            sys.exit('WeatherFlow request failed with HTTP {}'.format(response.status_code))
        payload = response.json()
    except (requests.RequestException, ValueError):
        sys.exit('Unable to retrieve or parse WeatherFlow station metadata')

    status = payload.get('status', {}).get('status_message', '')
    if 'SUCCESS' not in status:
        sys.exit('WeatherFlow rejected the metadata request')

    try:
        updates = metadata_updates(config, payload)
    except ValueError as error:
        sys.exit(str(error))
    if not updates:
        print('WeatherFlow station/device metadata is already complete.')
        return

    for key, value in updates.items():
        config.set('Station', key, str(value))

    config_dir = os.path.dirname(os.path.abspath(args.config))
    descriptor, temporary = tempfile.mkstemp(prefix='wfpiconsole-', suffix='.ini',
                                             dir=config_dir, text=True)
    try:
        with os.fdopen(descriptor, 'w') as config_file:
            config.write(config_file)
        os.replace(temporary, args.config)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

    print('Updated: {}'.format(', '.join(sorted(updates))))


if __name__ == '__main__':
    main()
