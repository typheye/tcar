#!/bin/sh
set -u
CONFIG=$(dirname "$0")/../media/network.yaml
IFACE=$(awk -F: '$1 ~ /^[[:space:]]*interface[[:space:]]*$/ {gsub(/[[:space:]\"]/,"",$2); print $2; exit}' "$CONFIG")
IFACE=${IFACE:-wlan0}
exec /sbin/wpa_supplicant -c/etc/wpa_supplicant/wpa_supplicant.conf -Dnl80211,wext -i"$IFACE"
