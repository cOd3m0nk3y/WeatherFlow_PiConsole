import configparser
import unittest

from tools.add_fork_settings import add_fork_settings, ordered_config


class AddForkSettingsTests(unittest.TestCase):

    def make_config(self):
        config = configparser.ConfigParser(allow_no_value=True)
        config.optionxform = str
        config.read_dict({
            'Keys': {'WeatherFlow': 'secret'},
            'PrimaryPanels': {'PanelThree': 'WindSpeed'},
            'SecondaryPanels': {'PanelThree': ''},
            'System': {'Version': 'v26.4.2'},
        })
        return config

    def test_adds_defaults_and_panel_cycle_without_touching_existing_values(self):
        config = self.make_config()

        changes = add_fork_settings(config)

        self.assertIn('Keys.AirNow', changes)
        self.assertEqual(config['Keys']['WeatherFlow'], 'secret')
        self.assertEqual(config['SecondaryPanels']['PanelThree'], 'AirNow')
        self.assertEqual(config['TertiaryPanels']['PanelThree'], 'Radar')
        self.assertEqual(config['TertiaryPanels']['PanelFour'], 'ExtendedForecast')
        self.assertEqual(config['Display']['RainfallPanel'], '1')
        self.assertEqual(config['Display']['rainfall_timeout'], '15')

    def test_preserves_existing_airnow_key(self):
        config = self.make_config()
        config['Keys']['AirNow'] = 'keep-me'

        add_fork_settings(config)

        self.assertEqual(config['Keys']['AirNow'], 'keep-me')

    def test_places_feature_sections_with_panel_sections(self):
        config = self.make_config()
        add_fork_settings(config)

        sections = ordered_config(config).sections()

        self.assertLess(sections.index('AirNow'), sections.index('PrimaryPanels'))
        self.assertLess(sections.index('Radar'), sections.index('PrimaryPanels'))
        self.assertEqual(sections.index('TertiaryPanels'),
                         sections.index('SecondaryPanels') + 1)


if __name__ == '__main__':
    unittest.main()
