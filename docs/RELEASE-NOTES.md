# AHAS 2.0 — Made by Ahas Nimsandu

- New **.ahas v2** format with solid XZ/LZMA2 compression, whole-file deduplication, and zero-run elision. No per-chunk SQLite container overhead.
- Separate, explicitly **lossy Media Optimizer**, using macOS `sips` for still-image JPEG output and `avconvert` for MP4/M4V/MOV inputs to MOV output.
- Smallest / Balanced / More Detail quality presets; originals are untouched. Failed or larger conversions are replaced with an unchanged original copy in the output folder.
- Ivory, deep navy, emerald, and muted-gold interface; creator credit in the header, footer, window title, and About dialog.
- Legacy .cla archives can still be extracted and verified.
- Native Mac packaging workflow: app, DMG, ZIP, checksums, tests, and Apple code-signature verification.

## Important

Apple Silicon build target: macOS 11+. Minimum-OS compatibility and native UI require real-Mac testing. Ad-hoc signed only: **not Developer ID signed or notarized**. A successful automated packaging run is not a comprehensive GUI or compatibility test.

Lossless compression cannot guarantee a reduction for arbitrary input. Already-compressed files may grow slightly. Media optimization is irreversible and may change resolution, quality, metadata, color, transparency, animation, HDR, and audio/video tracks. Support depends on macOS codecs; audio-only files are not handled.

The Linux-generated development DMG and ZIP are structurally checked but are not an Apple-certified release. Prefer the native-macOS workflow artifacts after its tests succeed. Always test restoration and keep independent backups.
