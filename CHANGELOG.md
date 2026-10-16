# Changelog

## 2.0.1

- Embed the bundled interpreter in the native launcher, preserving the AHAS app/menu/NSBundle identity instead of replacing the process with the Python executable.
- Record successful native macOS build, media/image tests, Apple signature/DMG checks, and packaged-app restoration smoke testing.

## 2.0.0

- New AHAS branding and ivory/navy/emerald/gold interface; author credit remains visible.
- New `.ahas` v2 format: solid XZ/LZMA2, compact framing, whole-file deduplication, zero runs, per-file BLAKE2b integrity.
- Balanced and maximum strength profiles; honest warning when an archive does not shrink.
- Separate, explicitly lossy Media Optimizer for supported images and video using macOS system tools.
- Original files untouched; converted files that grow or fail are replaced with unchanged output copies and reported.
- Legacy `.cla` extraction/verification retained.
- Archive, media-control-flow, HTTP, and browser tests; synthetic comparisons against legacy/ZIP.
- Native macOS build script and CI/release workflows.

## 1.1.0

- Experimental bundled-runtime Apple Silicon app/DMG and creator tag.

## 1.0.0

- Original local web app with per-chunk LZMA, SQLite container, chunk deduplication, and verification.
