#!/bin/bash
# Native macOS packaging; requires Python 3.11+ and Xcode Command Line Tools on BUILD machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
if [ "$(uname -s)" != Darwin ]; then echo 'Run this builder on macOS.' >&2; exit 1; fi
OUT="${1:-$ROOT/release}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd -P)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ahas-build.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cd "$ROOT"
python3 -m unittest discover -s "$ROOT/tests" -v
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install --disable-pip-version-check 'Pillow==12.3.0' 'ds_store==1.3.3'
URL='https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.13.16%2B20261013-aarch64-apple-darwin-install_only_stripped.tar.gz'
EXPECTED='16a5332fb0dcb77f163fc8f8cbccd95be1644cc53e68e5d2a79f50afd6680a0e'
curl --fail --location --retry 3 "$URL" -o "$WORK/runtime.tar.gz"
printf '%s  %s\n' "$EXPECTED" "$WORK/runtime.tar.gz" | shasum -a 256 -c -
tar -xzf "$WORK/runtime.tar.gz" -C "$WORK"
xcrun clang -arch arm64 -mmacosx-version-min=11.0 -O2 "$ROOT/macos/launcher.c" -o "$WORK/AHAS-launcher"
"$WORK/venv/bin/python" "$ROOT/macos/assemble_bundle.py" "$WORK"
python3 - "$WORK" <<'PY'
from pathlib import Path
import json,sys
work=Path(sys.argv[1])
for item in json.loads((work/'symlinks.json').read_text()):
    p=work/'stage'/item['path'].lstrip('/')
    p.symlink_to(item['target'])
PY
APP="$WORK/stage/AHAS.app"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
python3 "$ROOT/macos/verify_bundle.py" "$APP"
if [ "$(uname -m)" = arm64 ]; then
  "$APP/Contents/Resources/python/bin/python3.13" -I -B -c 'import ctypes,lzma,sqlite3; print("Bundled runtime imports: OK")'
else
  echo 'Bundled arm64 runtime execution skipped on this Intel build runner.'
fi
DMG="$OUT/AHAS-2.0-AppleSilicon.dmg"
ZIP="$OUT/AHAS-2.0-AppleSilicon-App.zip"
[ ! -e "$DMG" ] && [ ! -e "$ZIP" ] || { echo 'Output exists; use an empty output folder.' >&2; exit 1; }
hdiutil create -volname 'AHAS - Ahas Nimsandu' -srcfolder "$WORK/stage" -fs HFS+ -format UDZO "$DMG"
hdiutil verify "$DMG"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
(cd "$OUT" && shasum -a 256 *.dmg *.zip > SHA256SUMS.txt)
echo "Built in $OUT. Ad-hoc only; NOT Developer ID signed or notarized. Native UI still needs manual Mac testing."
