import configparser
import unittest

from tools.repair_weatherflow_config import metadata_updates


class RepairWeatherFlowConfigTests(unittest.TestCase):

    def test_fills_only_missing_metadata_for_configured_tempest(self):
        config = configparser.ConfigParser()
        config.read_dict({'Station': {
            'StationID': '21498', 'TempestID': '71822', 'TempestSN': '',
            'TempestHeight': '', 'SkyID': '', 'SkySN': '', 'SkyHeight': '',
            'Latitude': '39.1', 'Longitude': '-104.1', 'Timezone': 'UTC',
            'Elevation': '2000', 'Name': 'Existing name',
        }})
        payload = {'stations': [{
            'station_id': 21498, 'name': 'API name', 'latitude': 40,
            'longitude': -105, 'timezone': 'America/Denver',
            'station_meta': {'elevation': 2010},
            'devices': [{'device_type': 'ST', 'device_id': 71822,
                         'serial_number': 'ST-0001',
                         'device_meta': {'agl': 2.5}}],
        }]}

        updates = metadata_updates(config, payload)

        self.assertEqual(updates, {'TempestSN': 'ST-0001',
                                   'TempestHeight': 2.5})


if __name__ == '__main__':
    unittest.main()
