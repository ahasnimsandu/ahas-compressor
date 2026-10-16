# AHAS 2.0 macOS builds

## Preferred: build on a real macOS runner

Run `bash macos/build-on-mac.sh` from a source checkout on a Mac with Python 3.11+ and Xcode Command Line Tools. The script changes to the source root, runs tests (including real `sips` and `avconvert`-preset tests on macOS), creates a temporary build venv with pinned Pillow/ds_store, downloads the exact checksum-pinned arm64 CPython runtime, compiles the arm64 launcher using Apple's SDK, assembles the bundle, restores symlinks, ad-hoc signs it using Apple's `codesign`, runs signature checks, and packages/validates a DMG with `hdiutil` plus an app ZIP with `ditto`. Outputs go in `release/` or a supplied empty destination folder.

`.github/workflows/macos-release.yml` performs this on a GitHub macOS runner after you push a `v*` tag or manually dispatch it. The bundled arm64 runtime is import-tested only when the runner itself is arm64; an Intel Mac can compile/package the target but cannot execute that arm64 runtime. The workflow does not automate native GUI startup or guarantee macOS 11 compatibility.

These are ad-hoc signatures, not Developer ID trust or notarization. For a trusted public distribution, run native UI/media/restore tests, use your own Developer ID signing identity, notarize/staple the release on macOS, and verify Gatekeeper assessment. No certificate or private key is included.

## Runtime and source layout

- `RUNTIME-PROVENANCE.json`: exact upstream CPython 3.13.16 arm64 archive, release digest, and source URL. The builder checks that SHA256 before extraction.
- `runtime-licenses/`: upstream license collection. Optional components listed there are not necessarily all used.
- `launcher.c`: native launcher that embeds bundled CPython using its isolated PyConfig API. It preserves the AHAS NSBundle/menu identity; no Terminal window or interpreter exec replacement.
- `launch.sh`: optional source/debug launcher; packaged builds embed Python directly and log outside the read-only bundle.
- `native_host.py`: AppKit/WebKit host, native menus/author About, local server, cancellation/quit lifecycle.
- `assemble_bundle.py`: build-only helper. `work/python/` and `work/AHAS-launcher` must exist. It stages `work/stage/AHAS.app`, records/removes symlinks in `work/symlinks.json` for the Linux importer, and creates the icon/Finder layout. Restore those links before signing or Mac packaging.
- `verify_bundle.py`: independent resource and Mach-O page-hash structural checks, not Apple's Gatekeeper/trust validation.

## Linux development artifact

Earlier development DMGs were cross-built using clang/ld64.lld, a public libSystem stub, `rcodesign` recursive ad-hoc signing, `mkfs.hfsplus`, and a `planetbeing/libdmg-hfsplus` importer/UDIF writer (commit `7ac55ec64c96f7800d9818ce64c79670e7f02b67`, optional legacy OpenSSL FileVault disabled, HFS partition label corrected from hardcoded HFSX to HFS). Independent `dmg2img` decoding and filesystem checks are used afterward. Build tools are not runtime dependencies and are not redistributed in the app.

A standalone app ZIP is also provided to avoid the disk-image step. It preserves executable bits and nine runtime symlinks. This does not bypass or repair a signing/security issue.

The exact delivered artifact hashes/checks are in `BUILD-RECEIPT.json`. Resource/page hashes and a filesystem checker cannot certify native startup, media codec behavior, Apple code-signing acceptance, or mounting on a real Mac. `rcodesign verify` is not used as Apple trust evidence; its ad-hoc CMS verification is documented as unreliable.
