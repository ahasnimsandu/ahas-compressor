# AHAS 2.0.1 — Tests and benchmarks

## Native macOS release

[Release build](https://github.com/ahasnimsandu/ahas-compressor/actions/runs/38961746861) · [Downloads and checksums](https://github.com/ahasnimsandu/ahas-compressor/releases/tag/v2.0.1)

The release was built on an Apple Silicon macOS runner.

- **61 tests passed**, including `sips` image conversion and `avconvert` preset enumeration.
- Bundled arm64 Python imports passed for `ctypes`, `lzma`, and `sqlite3`.
- Apple's `codesign --verify --deep --strict` verified the ad-hoc signature.
- `hdiutil verify` checked the DMG and partition checksums.
- The packaged app launched and completed archive creation, verification, and extraction with byte-identical recovery, including a Unicode filename.
- The captured [Mac screenshot](docs/screenshots/native-mac.png) shows the interface and AHAS menu identity.
- Downloaded DMG and ZIP hashes matched the published checksums. See `macos/BUILD-RECEIPT.json` for artifact details.

## Cross-platform and browser tests

[Cross-platform CI](https://github.com/ahasnimsandu/ahas-compressor/actions/runs/38960175273) passed on Linux and macOS with Python 3.11 and 3.13.

The Linux Python 3.13.16 run discovered 61 tests: 59 passed and two macOS-only tests were skipped. Coverage includes archive framing, round trips, duplicates, zero runs, corruption, path safety, cancellation, legacy `.cla` reading, media orchestration, HTTP authentication, and lossy-consent checks.

Chromium tests cover the creator credit, mode selection, lossy consent, archive creation/verification/extraction, restored-byte comparison, JavaScript errors, and layout at a 390 px viewport.

## Coverage limits

- No full native file-dialog automation or minimum-macOS-11 compatibility test.
- No actual video transcode or all-codec compatibility test; video testing covers preset enumeration and orchestration.
- No end-user Gatekeeper/quarantine approval test. Ad-hoc signing is not Developer ID signing or notarization.
- No 50 GB benchmark or maximum-level performance benchmark. Functional tests cover balanced and fast settings.

## Compression benchmarks

AHAS uses solid XZ preset 6; legacy CLA uses per-chunk XZ preset 3 plus chunk dedup; ZIP uses DEFLATE-6. AHAS fingerprinting time is included. Codec, preset, dedup granularity, and container overhead all differ. Selected deterministic inputs are illustrative, not universal.

| Dataset | Input B | AHAS v2 B | Legacy CLA B | ZIP B | AHAS s | ZIP s |
|---|---:|---:|---:|---:|---:|---:|
| zero-filled | 67,108,864 | 336 | 36,864 | 65,372 | 0.3935 | 0.2896 |
| duplicate-binaries | 16,777,216 | 1,049,388 | 1,085,440 | 16,784,534 | 0.3127 | 0.4343 |
| unique-random | 8,388,608 | 8,389,480 | 8,433,664 | 8,391,314 | 3.1671 | 0.2130 |
| repetitive-text | 6,300,000 | 1,384 | 36,864 | 18,554 | 0.1458 | 0.0273 |
| already-compressed | 4,195,702 | 4,196,380 | 4,235,264 | 4,197,138 | 1.2378 | 0.1025 |
| many-small-text-files | 301,840 | 12,036 | 98,304 | 32,612 | 0.0304 | 0.0133 |

Every AHAS test archive was fully verified. Media quality and output-size benchmarks are not available.

## Interpretation

- New framing dramatically reduces the old SQLite overhead on small archives.
- Solid compression helps repetitive text and collections of small related files.
- Whole-file duplicates and zero runs compress exceptionally well by construction.
- Random/already-compressed inputs still grow slightly. ZIP is substantially faster on random input in this run.
- Partial duplicates can favor the legacy chunk-dedup design; AHAS v2 is not universally better.
