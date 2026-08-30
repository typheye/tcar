#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -m 0644 "$BASE/systemd/wlan-helper.service" /etc/systemd/system/wlan-helper.service
install -m 0644 "$BASE/systemd/tcar-core.service" /etc/systemd/system/tcar-core.service
install -m 0644 "$BASE/systemd/set-eth-speed.service" /etc/systemd/system/set-eth-speed.service
chmod 0755 "$BASE/wlan-helper.sh"
systemctl daemon-reload
systemctl enable --now set-eth-speed.service wlan-helper.service tcar-core.service
