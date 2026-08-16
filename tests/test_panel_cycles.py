import unittest

from lib.panel_cycles import rainfall_takeover_button


def entry(name, cycle, index=0):
    return [name, 'panel', cycle[0], cycle[1] if len(cycle) > 1 else '',
            'primary' if index == 0 else 'secondary', cycle, index]


class PanelCycleTests(unittest.TestCase):

    def test_finds_rainfall_in_any_non_primary_cycle_position(self):
        buttons = [entry('one', ['Temperature', 'AirNow']),
                   entry('five', ['DailyTemperature', 'Radar', 'Rainfall'])]

        self.assertEqual(rainfall_takeover_button(buttons)[0], 'five')

    def test_does_not_take_over_when_rainfall_is_any_primary_panel(self):
        buttons = [entry('one', ['Rainfall', 'DailyTemperature']),
                   entry('five', ['DailyTemperature', 'Rainfall'])]

        self.assertIsNone(rainfall_takeover_button(buttons))

    def test_returns_none_when_rainfall_is_not_configured(self):
        self.assertIsNone(rainfall_takeover_button([
            entry('one', ['DailyTemperature', 'Radar'])]))


if __name__ == '__main__':
    unittest.main()
