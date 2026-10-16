#!/bin/bash
# Finder-compatible launcher. No downloads, package installs, or administrator access.
cd "$(dirname "$0")" || exit 1
PYTHON=""
for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  printf '\nAHAS needs Python 3.11 or newer.\n\nInstall the macOS Python package from https://www.python.org/downloads/macos/\nThen double-click this launcher again.\n\nNo Python packages or administrator access are needed by AHAS itself.\n'
  read -r -p 'Press Return to close… ' ignored
  exit 1
fi
"$PYTHON" -m compactlocal
result=$?
if [ "$result" -ne 0 ]; then
  printf '\nAHAS could not start (exit %s).\n' "$result"
  read -r -p 'Press Return to close… ' ignored
fi
exit "$result"
