#!/usr/bin/env bash
# Remove Python cache directories and bytecode from the workspace.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

find "$BASE_DIR" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$BASE_DIR" -type f -name '*.pyc' -delete

echo "[OK] Python cache cleaned."
