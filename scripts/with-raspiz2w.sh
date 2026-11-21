#!/usr/bin/env bash
# Linux counterpart of with-raspiz2w.bat, matching the 4B helper's options.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
TARGET_DIR="/home/pi"
SERVICE="tcar.service"

show_help() {
    cat <<'EOF'

Raspberry Pi Zero 2 W Debug Script
========================================================

Usage: scripts/with-raspiz2w.sh [OPTION]

Options:
  --reset  Upload tCar and restart tcar.service
  --ssh    Open SSH terminal to Zero 2 W
  --log    View tcar.service real-time logs
  --reboot Reboot Zero 2 W
  --format Remove /home/pi/tCar on Zero 2 W
  --help   Show this help message

Example: scripts/with-raspiz2w.sh --reset

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
    if not isinstance(payload, dict) or not isinstance(payload.get("devices"), list):
        raise ValueError("router response has no device list")
except Exception as error:
    print(f"failed to query {url}: {error}", file=sys.stderr)
    raise SystemExit(1)

for device in payload["devices"]:
    if not isinstance(device, dict) or device.get("name") != "Car device":
        continue
    if not device.get("status", True):
        continue
    try:
        address = ipaddress.ip_address(device.get("ip", ""))
    except ValueError:
        continue
    if address.version == 4 and not address.is_unspecified and not address.is_multicast:
        print(address)
        raise SystemExit(0)

print("Car device was not found online in the router response", file=sys.stderr)
raise SystemExit(1)
PY
}

update_restart() {
    if [[ ! -f "$BASE_DIR/tCar/init.py" ]]; then
        echo "[ERROR] Missing local tCar/init.py; refusing to upload." >&2
        exit 1
    fi
    echo "[1/2] Uploading tCar and restarting Zero 2 W service..."
    if ! tar --exclude='__pycache__' --exclude='*.pyc' \
        -C "$BASE_DIR" -cf - tCar | ssh "pi@$IP" "
        set -eu
        tar -C '$TARGET_DIR' -xf -
        sudo systemctl restart '$SERVICE'
        systemctl is-active --quiet '$SERVICE'
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
    echo "[ERROR] Car device discovery failed through http://192.168.66.1/test" >&2
    exit 1
fi
echo "[INFO] Car device: $IP"

case "$ACTION" in
    --reset)
        update_restart
        ;;
    --ssh)
        echo "Opening SSH terminal (Ctrl+D or exit to return)..."
        exec ssh "pi@$IP"
        ;;
    --log)
        echo "Viewing tcar.service real-time logs (Ctrl+C to exit)..."
        ssh "pi@$IP" "sudo journalctl -u '$SERVICE' -f"
        ;;
    --reboot)
        echo "Rebooting Zero 2 W..."
        ssh "pi@$IP" "sudo reboot"
        echo "[SUCCESS] Reboot command sent."
        ;;
    --format)
        echo "Removing /home/pi/tCar on Zero 2 W..."
        ssh "pi@$IP" "sudo rm -rf -- '/home/pi/tCar'"
        echo "[SUCCESS] Directory removed."
        ;;
esac
