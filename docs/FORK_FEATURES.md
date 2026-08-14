# AirNow, Radar, and Extended Forecast Panels

This fork adds three PiConsole panels while retaining the styling and panel
configuration used by the upstream WeatherFlow PiConsole:

- EPA AirNow observations and a station-centered air-quality contour map.
- NOAA/NWS radar with configurable radius, adaptive zoom, precipitation
  coverage, and an optional one-hour animation.
- A three-day detailed forecast followed by seven compact forecast days.

## Install this fork

The feature branch is published at
`cOd3m0nk3y/WeatherFlow_PiConsole:codex/airnow-radar-forecast-panels`.

For an existing Linux or Raspberry Pi installation:

```bash
cd ~/wfpiconsole
wfpiconsole stop
git remote set-url origin https://github.com/cOd3m0nk3y/WeatherFlow_PiConsole.git
git fetch origin
git switch --track origin/codex/airnow-radar-forecast-panels
venv/bin/python -m pip install "Pillow>=11.0"
wfpiconsole start
```

If the branch already exists locally, replace the `git switch --track` command
with:

```bash
git switch codex/airnow-radar-forecast-panels
git pull
```

For Windows:

```powershell
git clone --branch codex/airnow-radar-forecast-panels --single-branch `
  https://github.com/cOd3m0nk3y/WeatherFlow_PiConsole.git
cd WeatherFlow_PiConsole
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install websockets "Pillow>=11.0" numpy pytz tzlocal ephem packaging cryptography pyOpenSSL certifi "kivy[base]"
.\venv\Scripts\python.exe main.py
```

Never commit `wfpiconsole.ini`; it contains private API and station details and
is ignored by Git.

## Configuration migration

On startup, the fork compares `wfpiconsole.ini` with its configuration schema.
Missing sections and options are added automatically even when the upstream
PiConsole version has not changed. Existing API keys, station information,
units, panel selections, and other values are preserved.

This makes all of the following safe:

- starting with a fresh configuration;
- copying an existing `wfpiconsole.ini` to another computer;
- switching an existing upstream installation to this fork.

## Manual INI configuration

Automatic migration is preferred. These are the feature-specific entries if
manual editing is required:

```ini
[Keys]
AirNow = YOUR_AIRNOW_API_KEY

[AirNow]
Radius = 25
RefreshInterval = 60

[Radar]
Radius = 50
ZoomOutLimit = 0
Animation = 0
RefreshInterval = 5

[TertiaryPanels]
PanelThree = Radar
PanelFour = ExtendedForecast
```

To create the Wind Speed → AirNow → Radar cycle, also set:

```ini
[SecondaryPanels]
PanelThree = AirNow
```

Do not replace complete existing sections with these snippets. Add or edit only
the listed options so other panel and credential settings remain intact.

### Radar options

- `Radius`: preferred map radius in miles.
- `ZoomOutLimit = 0`: zoom out until visible precipitation is found.
- `ZoomOutLimit = 1` or `2`: allow at most that many wider zoom levels.
- `Animation = 1`: loop available NOAA radar frames from approximately the
  previous hour; `0` shows only the latest frame.
- `RefreshInterval`: radar refresh interval in minutes.

### AirNow options

- `Radius`: local contour-map radius in miles.
- `RefreshInterval`: observation refresh interval in minutes. AirNow polling is
  clamped to a minimum of 60 minutes to protect API keys shared with other apps.

When current contour polygons are unavailable, the AirNow panel uses a uniform,
translucent tint matching the current reporting-area AQI. The panel labels this
as an area AQI tint so it is not mistaken for a spatial contour. Rate-limited or
failed observation updates retain the last reading and mark it as stale.
- `RefreshInterval`: observation and map refresh interval in minutes.
- `Keys.AirNow`: API key obtained from AirNowAPI.org.

The same values can be changed from the PiConsole settings screen.
