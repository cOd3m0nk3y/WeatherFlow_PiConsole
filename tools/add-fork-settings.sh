#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ -x "venv/Scripts/python.exe" ]]; then
    python_cmd="venv/Scripts/python.exe"
elif [[ -x "venv/bin/python" ]]; then
    python_cmd="venv/bin/python"
else
    python_cmd="python"
fi

"$python_cmd" tools/add_fork_settings.py "$@"
