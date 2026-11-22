#!/usr/bin/env bash
# Compatibility entry point; implementation is shared with Windows.
set -euo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/pc.sh" build "$@"
