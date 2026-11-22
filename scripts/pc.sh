#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/manage.py" "$@"
elif command -v conda >/dev/null 2>&1; then
    exec conda run --no-capture-output -n base python "$SCRIPT_DIR/manage.py" "$@"
else
    echo "[ERROR] Python 3 or Conda is required." >&2
    exit 1
fi
