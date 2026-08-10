#!/usr/bin/env bash

# Complete WeatherFlow metadata setup for an existing local PiConsole install.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ -x "venv/Scripts/python.exe" ]]; then
    python_cmd="venv/Scripts/python.exe"
elif [[ -x "venv/bin/python" ]]; then
    python_cmd="venv/bin/python"
else
    echo "No project virtual environment found."
    echo "Create one with: python -m venv venv"
    exit 1
fi

if [[ ! -f "wfpiconsole.ini" ]]; then
    echo "wfpiconsole.ini is missing. Start main.py to run the full wizard first."
    exit 1
fi

backup="wfpiconsole.backup.$(date +%Y%m%d-%H%M%S).ini"
cp -p "wfpiconsole.ini" "$backup"
echo "Backed up configuration to $backup"

echo "Completing WeatherFlow station/device metadata..."
"$python_cmd" tools/repair_weatherflow_config.py --config wfpiconsole.ini

echo
echo "Local setup is complete. Start PiConsole with:"
echo "  $python_cmd main.py"
