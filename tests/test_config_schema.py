import configparser
import unittest

from lib.config import default_config_file, merge_missing_defaults


class ConfigSchemaTests(unittest.TestCase):

    def test_adds_fork_sections_without_overwriting_existing_values(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_dict({
            'Keys': {'WeatherFlow': 'keep-secret'},
            'PrimaryPanels': {'PanelThree': 'MyCustomPanel'},
            'System': {'Version': default_config_file()['System']['Version']['value'],
                       'rest_api': '0'},
        })

        merge_missing_defaults(config)

        self.assertEqual(config['Keys']['WeatherFlow'], 'keep-secret')
        self.assertEqual(config['Keys']['AirNow'], '')
        self.assertEqual(config['PrimaryPanels']['PanelThree'], 'MyCustomPanel')
        self.assertEqual(config['AirNow']['Radius'], '25')
        self.assertEqual(config['Radar']['Radius'], '50')
        self.assertEqual(config['Radar']['ZoomOutLimit'], '0')
        self.assertEqual(config['Radar']['Animation'], '0')
        self.assertEqual(config['TertiaryPanels']['PanelThree'], 'Radar')
        self.assertEqual(config['TertiaryPanels']['PanelFour'],
                         'ExtendedForecast')

    def test_merge_is_idempotent(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_dict({'Radar': {'Radius': '100'}})

        merge_missing_defaults(config)
        first = {section: dict(config[section]) for section in config.sections()}
        merge_missing_defaults(config)

        self.assertEqual(first,
                         {section: dict(config[section])
                          for section in config.sections()})


if __name__ == '__main__':
    unittest.main()
