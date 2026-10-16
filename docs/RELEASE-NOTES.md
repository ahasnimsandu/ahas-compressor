# AHAS 2.0.1 — Made by Ahas Nimsandu

- New **.ahas v2** format with solid XZ/LZMA2 compression, whole-file deduplication, and zero-run elision. No per-chunk SQLite container overhead.
- Separate, explicitly **lossy Media Optimizer**, using macOS `sips` for still-image JPEG output and `avconvert` for MP4/M4V/MOV inputs to MOV output.
- Smallest / Balanced / More Detail quality presets; originals are untouched. Failed or larger conversions are replaced with an unchanged original copy in the output folder.
- Ivory, deep navy, emerald, and muted-gold interface; creator credit in the header, footer, window title, and About dialog.
- Legacy .cla archives can still be extracted and verified.
- Native Mac packaging workflow: app, DMG, ZIP, checksums, tests, and Apple code-signature verification.

## Important

Apple Silicon build target: macOS 11+. Minimum-OS compatibility and native UI require real-Mac testing. Ad-hoc signed only: **not Developer ID signed or notarized**. A successful automated packaging run is not a comprehensive GUI or compatibility test.

Lossless compression cannot guarantee a reduction for arbitrary input. Already-compressed files may grow slightly. Media optimization is irreversible and may change resolution, quality, metadata, color, transparency, animation, HDR, and audio/video tracks. Support depends on macOS codecs; audio-only files are not handled.

The DMG and ZIP are built on Apple Silicon macOS. [Release build and archive/restore tests](https://github.com/ahasnimsandu/ahas-compressor/actions/runs/38961746861) passed. Keep independent backups and test restoration before deleting originals.

## Native Mac validation

The release workflow runs all 61 tests on macOS, Apple's strict ad-hoc signature verification, bundled-runtime imports, and hdiutil DMG verification. On an arm64 runner it also launches the actual packaged native app and exercises its .ahas compression/verification/extraction backend, comparing restored bytes. A screenshot is captured for visual review. This is not full GUI/file-dialog or all-codec automation and does not grant notarization or Developer ID trust.

2.0.1 embeds the interpreter in the native executable so the app/menu retains its AHAS identity instead of appearing as python3.13.
