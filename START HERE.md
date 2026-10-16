# AHAS 2.0.1

Made by Ahas Nimsandu

## Install

Open the Apple Silicon DMG and drag **AHAS.app** into **Applications**. Alternatively, extract the app ZIP and move the app there. Python is bundled; no additional installation is needed.

The app is ad-hoc signed, not Developer ID signed or notarized. If macOS blocks it, check the download checksum and the installation notes in README.md. Do not disable Gatekeeper globally.

## Choose a mode

- **Lossless Archive:** create `.ahas` archives with exact file-byte recovery. Use **Verify** and test **Extract** before deleting originals. Existing `.cla` archives remain readable.
- **Media Optimizer:** create smaller image and video copies with adjustable quality. This mode is lossy and requires confirmation. Originals stay untouched. If a conversion fails or produces a larger file, an unchanged copy is saved instead.

Compression depends on the input. Archives do not preserve resource forks, extended attributes, or Finder tags; AHAS is not a full-system backup tool.

## Run from source

With Python 3.11+, double-click `Start AHAS.command` or run `python3 -m compactlocal`. The source edition opens in a browser. Media optimization requires macOS.

- [Full documentation](README.md)
- [Tests and benchmarks](VALIDATION.md)
- [Mac build instructions](macos/BUILD-NOTES.md)
