"""Add the fork panel settings to an existing wfpiconsole.ini."""

import argparse
import configparser
import os
import shutil
from datetime import datetime


FEATURE_SETTINGS = {
    'Keys': {'AirNow': ''},
    'Display': {'RainfallPanel': '1', 'rainfall_timeout': '15'},
    'AirNow': {'Radius': '25', 'RefreshInterval': '60'},
    'Radar': {
        'Radius': '50',
        'ZoomOutLimit': '0',
        'Animation': '0',
        'RefreshInterval': '5',
    },
    'SecondaryPanels': {'PanelThree': 'AirNow'},
    'TertiaryPanels': {
        'PanelThree': 'Radar',
        'PanelFour': 'ExtendedForecast',
    },
}


def add_fork_settings(config):
    """Add feature defaults and return the names of changed settings."""

    changes = []
    for section, options in FEATURE_SETTINGS.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in options.items():
            # Never erase an API key that is already configured.
            if section == 'Keys' and key == 'AirNow' and config.has_option(section, key):
                continue
            if config.get(section, key, fallback=None) != value:
                config.set(section, key, value)
                changes.append('{}.{}'.format(section, key))
    return changes


def ordered_config(config):
    """Place fork sections alongside the related built-in sections."""

    desired = []
    source_sections = config.sections()
    for section in source_sections:
        if section in ('AirNow', 'Radar', 'TertiaryPanels'):
            continue
        if section == 'PrimaryPanels':
            desired.extend(('AirNow', 'Radar'))
        desired.append(section)
        if section == 'SecondaryPanels':
            desired.append('TertiaryPanels')

    for section in ('AirNow', 'Radar', 'TertiaryPanels'):
        if section not in desired:
            desired.append(section)

    result = configparser.ConfigParser(allow_no_value=True)
    result.optionxform = str
    for section in desired:
        if not config.has_section(section):
            continue
        result.add_section(section)
        for key, value in config.items(section, raw=True):
            result.set(section, key, value)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Add fork panel and automatic rainfall settings.')
    parser.add_argument('--config', default='wfpiconsole.ini')
    args = parser.parse_args()

    path = os.path.abspath(args.config)
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = str
    if not config.read(path):
        parser.error('configuration file not found: {}'.format(path))

    changes = add_fork_settings(config)
    updated_config = ordered_config(config)
    reordered = config.sections() != updated_config.sections()
    if not changes and not reordered:
        print('Fork settings are already configured.')
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = '{}.backup-{}'.format(path, stamp)
    shutil.copy2(path, backup)

    with open(path, 'w') as config_file:
        updated_config.write(config_file)

    print('Backup: {}'.format(backup))
    if changes:
        print('Updated: {}'.format(', '.join(changes)))
    if reordered:
        print('Reordered fork sections beside the panel configuration.')
    if not config.get('Keys', 'AirNow', fallback='').strip():
        print('Next: add your API key to Keys.AirNow in {}'.format(path))


if __name__ == '__main__':
    main()
