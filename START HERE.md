# AHAS 2.0 — Made by Ahas Nimsandu

## Packaged Apple Silicon app

Open the DMG and drag AHAS.app to Applications, or unzip the app ZIP and move AHAS.app there. Python is bundled; no installation or account is needed. This development build is ad-hoc signed/not notarized and has not been executed on a real Mac here. Do not disable macOS security globally if it is blocked.

## Two modes

- **Lossless Archive:** exact supported regular-file bytes, stronger solid compression, new `.ahas` format. Use Verify and test Extract before deleting originals. Legacy `.cla` archives remain readable.
- **Media Optimizer:** explicitly lossy smaller copies for supported still images and MP4/MOV/M4V video. Choose a quality preset and accept the warning. Originals stay untouched. Files that do not get smaller or fail conversion are copied unchanged instead.

No compression method guarantees 50 GB → 50 MB for arbitrary files. Mac extended metadata/resource forks are not preserved; this is not a full backup utility.

## Source package

Python 3.11+ can launch the local browser edition with `Start AHAS.command` or `python3 -m compactlocal`. Media optimization requires macOS.

For GitHub, inspect and run `Publish to GitHub.command` after installing GitHub CLI. It authenticates on your Mac, defaults to a private repository, and can request the included native-Mac release workflow. Upstream: https://github.com/ahasnimsandu/ahas-compressor

Full instructions: README.md. Tests/measurements: VALIDATION.md. Native packaging: macos/BUILD-NOTES.md.
