#!/usr/bin/env bash
# Clean only Python caches belonging to the Zero 2 W application.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
APP_DIR="$BASE_DIR/tCar"

if [[ ! -f "$APP_DIR/init.py" ]]; then
    echo "[ERROR] Missing tCar/init.py; refusing to clean an unknown directory." >&2
    exit 1
fi

find "$APP_DIR" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$APP_DIR" -type f -name '*.pyc' -delete

echo "[OK] tCar Python cache cleaned."
