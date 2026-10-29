#!/usr/bin/env bash
# Raspberry Pi deployment helper for Linux.
#
# Mirrors scripts/with-raspi4b.bat: upload and restart, SSH, logs, reboot,
# and remote cleanup are exposed through the same command-line options.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
TARGET_DIR="/home/pi"
SERVICE="tcar-core.service"

show_help() {
    cat <<'EOF'

Raspberry Pi Debug Script
========================================================

Usage: scripts/with-raspi4b.sh [OPTION]

Options:
  --reset  Upload and restart tCarCore service
  --ssh    Open SSH terminal to Raspberry Pi
  --log    View tcar-core.service real-time logs
  --reboot Reboot Raspberry Pi
  --format Remove ~/tCarCore directory on Raspberry Pi
  --help   Show this help message

Example: scripts/with-raspi4b.sh --reset

EOF
}

discover_host() {
    python3 - <<'PY'
import ipaddress
import json
import sys
import urllib.request

url = "http://192.168.66.1/test"
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        payload = json.load(response)
except Exception as error:
    print(f"failed to query {url}: {error}", file=sys.stderr)
    raise SystemExit(1)

for device in payload.get("devices", []):
    if device.get("name") != "Core host":
        continue
    try:
        address = ipaddress.ip_address(device.get("ip", ""))
    except ValueError:
        continue
    print(address)
    raise SystemExit(0)

print("Core host was not found in the router response", file=sys.stderr)
raise SystemExit(1)
PY
}

remove_local_python_cache() {
    find "$BASE_DIR/tCarCore" -type d -name __pycache__ -prune \
        -exec rm -rf -- {} +
    find "$BASE_DIR/tCarCore" -type f -name '*.pyc' -delete
}

update_restart() {
    echo "[1/2] Uploading files and restarting Raspberry Pi service..."
    remove_local_python_cache
    if ! tar -C "$BASE_DIR" -cf - tCarCore | ssh "pi@$IP" "
        set -e
        tar -C $TARGET_DIR -xf -
        rm -f ~/tCarCore/Utils/dmp_firmware.bin
        sudo systemctl restart $SERVICE
        systemctl is-active --quiet $SERVICE
    "; then
        echo "[ERROR] Upload/restart failed; check the SSH output above." >&2
        exit 1
    fi
    echo "[2/2] Service is active."
    echo "[SUCCESS] Service restarted."
}

ACTION="${1:---help}"
if [[ $# -gt 1 ]]; then
    echo "[ERROR] Only one option may be supplied." >&2
    show_help
    exit 2
fi

case "$ACTION" in
    --help|-h)
        show_help
        exit 0
        ;;
    --reset|--ssh|--log|--reboot|--format)
        ;;
    *)
        echo "[ERROR] Unknown option: $ACTION" >&2
        show_help
        exit 2
        ;;
esac

if ! IP="$(discover_host)"; then
    echo "[ERROR] Core host discovery failed through http://192.168.66.1/test" >&2
    exit 1
fi
echo "[INFO] Core host: $IP"

case "$ACTION" in
    --reset)
        update_restart
        ;;
    --reboot)
        echo "Rebooting Raspberry Pi..."
        if ! ssh "pi@$IP" "sudo reboot"; then
            echo "[INFO] SSH closed after sending the reboot request."
        fi
        echo "[SUCCESS] Reboot command sent."
        ;;
    --ssh)
        echo "================================"
        echo "Opening SSH Terminal"
        echo "================================"
        echo "Press Ctrl+D or type 'exit' to return"
        echo "================================"
        exec ssh "pi@$IP"
        ;;
    --format)
        echo "Formatting Raspberry Pi directory..."
        ssh "pi@$IP" "sudo rm -rf ~/tCarCore"
        echo "[SUCCESS] Directory removed."
        ;;
    --log)
        echo "================================"
        echo "Viewing tcar-core.service real-time logs"
        echo "================================"
        echo "Press Ctrl+C to exit log view"
        echo "================================"
        ssh "pi@$IP" "sudo journalctl -u $SERVICE -f"
        ;;
esac
