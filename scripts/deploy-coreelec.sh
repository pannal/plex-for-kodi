#!/bin/sh
set -eu

HOST="${1:-root@192.168.1.201}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TARGET="/storage/.kodi/addons/script.plexmod"

ssh "$HOST" \
    "mkdir -p '$TARGET' && rm -rf '$TARGET/lib' '$TARGET/resources'"

scp -r \
    "$ROOT/addon.xml" \
    "$ROOT/changelog.txt" \
    "$ROOT/default.py" \
    "$ROOT/fanart.png" \
    "$ROOT/icon2.png" \
    "$ROOT/lib" \
    "$ROOT/LICENSE.txt" \
    "$ROOT/plugin.py" \
    "$ROOT/resources" \
    "$ROOT/screensaver.py" \
    "$ROOT/service.py" \
    "$HOST:$TARGET/"

ssh "$HOST" \
    "rm -f '$TARGET/resources/skins/Main/1080i/script-plex-seek_dialog.xml' && systemctl restart kodi"

printf 'Deployed script.plexmod to %s and restarted Kodi.\n' "$HOST"
