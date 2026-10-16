# Changelog

## 2.0.0

- New AHAS branding and ivory/navy/emerald/gold interface; author credit remains visible.
- New `.ahas` v2 format: solid XZ/LZMA2, compact framing, whole-file deduplication, zero runs, per-file BLAKE2b integrity.
- Balanced and maximum strength profiles; honest warning when an archive does not shrink.
- Separate, explicitly lossy Media Optimizer for supported images and video using macOS system tools.
- Original files untouched; converted files that grow or fail are replaced with unchanged output copies and reported.
- Legacy `.cla` extraction/verification retained.
- Archive, media-control-flow, HTTP, and browser tests; synthetic comparisons against legacy/ZIP.
- Native-macOS build script, CI/release workflows, GitHub publishing guide and guided publisher.
- Public repository published with owner-approved GitHub CLI device authentication: ahasnimsandu/ahas-compressor. A publishing helper is also included for forks/copies.

## 1.1.0

- Experimental bundled-runtime Apple Silicon app/DMG and creator tag.

## 1.0.0

- Original local web app with per-chunk LZMA, SQLite container, chunk deduplication, and verification.
