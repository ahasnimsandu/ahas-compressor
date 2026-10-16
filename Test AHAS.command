#!/bin/bash
cd "$(dirname "$0")" || exit 1
python3 -m unittest discover -s tests -v
status=$?
printf '\nTest exit code: %s\n' "$status"
read -r -p 'Press Return to close… ' ignored
exit "$status"
