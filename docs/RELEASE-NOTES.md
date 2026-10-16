# AHAS 2.0.2

Made by Ahas Nimsandu

- Updated the README, installation notes, and developer documentation.
- Simplified in-app descriptions and removed the repository-publishing helper.
- Refreshed bundled documentation in the Apple Silicon app and DMG.
- No changes to archive format, compression settings, or media conversion behavior.

## Installation

Open the DMG and drag AHAS.app into Applications, or extract the app ZIP and move the app there. The arm64 Python runtime is bundled.

Apple Silicon; macOS 11+ build target. Ad-hoc signed only, not Developer ID signed or notarized. Minimum-OS compatibility and end-user Gatekeeper approval require separate testing.

## File handling

Lossless Archive creates `.ahas` files with exact supported file-byte recovery. Media Optimizer is lossy and can change quality, resolution, metadata, color, and audio/video tracks. It requires confirmation and leaves originals untouched. Compression ratios depend on the input; already-compressed files may not shrink.

Keep independent backups and test extraction before deleting originals. See README.md and VALIDATION.md for supported metadata and test coverage.
