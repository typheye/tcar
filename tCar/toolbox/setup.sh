#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -m 0644 "$BASE/systemd/set-eth-speed.service" /etc/systemd/system/set-eth-speed.service
install -m 0644 "$BASE/systemd/tcar.service" /etc/systemd/system/tcar.service
systemctl daemon-reload
systemctl enable --now set-eth-speed.service tcar.service
