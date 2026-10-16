#!/bin/sh
# Runs from an installed app or a read-only mounted DMG; no writes to the bundle.
umask 077
RESOURCES="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
LOGDIR="$HOME/Library/Logs/AHAS"
/bin/mkdir -p "$LOGDIR" || exit 1
exec >> "$LOGDIR/app.log" 2>&1
printf '\n--- AHAS · Made by Ahas Nimsandu ---\n'
exec "$RESOURCES/python/bin/python3.13" -I -B "$RESOURCES/native_host.py"
