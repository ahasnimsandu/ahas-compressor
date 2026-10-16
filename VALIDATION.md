# AHAS 2.0 validation

## Executed here

- Linux x86-64, Python 3.13.16.
- **61 tests discovered: 59 passed, 2 skipped.** Includes v2 framing/round trips/duplicates/zero runs/corruption/path safety/cancellation, legacy CLA, mocked media orchestration, HTTP auth/consent, and exact restoration.
- **Two skipped tests require real macOS:** actual `sips` conversion and `avconvert` preset enumeration. Mocked tests do not establish actual codec behavior.
- Chromium end-to-end test passed: visible author tag, lossless/media choices, lossy consent gate, .ahas creation → verification → extraction, byte comparison, 390px mobile width without overflow, no JavaScript page errors.
- Maximum level 9/EXTREME was not benchmarked here. Default balanced level 6 and fast level 1 are exercised.
- No 50 GB run was performed. Native arm64 execution, real-Mac DMG mounting, GUI/file dialogs, minimum macOS support, and actual media conversion were not performed in this environment.
- GitHub CI/native-Mac release workflows are included, but have not been run from this chat at the time this report was prepared.

## Synthetic benchmark (actual measured values)

AHAS uses solid XZ preset 6; legacy CLA uses per-chunk XZ preset 3 plus chunk dedup; ZIP uses DEFLATE-6. AHAS fingerprinting time is included. Codec, preset, dedup granularity, and container overhead all differ. Selected deterministic inputs are illustrative, not universal.

| Dataset | Input B | AHAS v2 B | Legacy CLA B | ZIP B | AHAS s | ZIP s |
|---|---:|---:|---:|---:|---:|---:|
| zero-filled | 67,108,864 | 336 | 36,864 | 65,372 | 0.3935 | 0.2896 |
| duplicate-binaries | 16,777,216 | 1,049,388 | 1,085,440 | 16,784,534 | 0.3127 | 0.4343 |
| unique-random | 8,388,608 | 8,389,480 | 8,433,664 | 8,391,314 | 3.1671 | 0.2130 |
| repetitive-text | 6,300,000 | 1,384 | 36,864 | 18,554 | 0.1458 | 0.0273 |
| already-compressed | 4,195,702 | 4,196,380 | 4,235,264 | 4,197,138 | 1.2378 | 0.1025 |
| many-small-text-files | 301,840 | 12,036 | 98,304 | 32,612 | 0.0304 | 0.0133 |

Every AHAS test archive was fully verified. Media optimization has no measured quality/size benchmark here.

## Interpretation

- New framing dramatically reduces the old SQLite overhead on small archives.
- Solid compression helps repetitive text and collections of small related files.
- Whole-file duplicates and zero runs compress exceptionally well by construction.
- Random/already-compressed inputs still grow slightly. ZIP is substantially faster on random input in this run.
- Partial duplicates can favor the legacy chunk-dedup design; AHAS v2 is not universally better.

## Packaging checks

See `macos/BUILD-RECEIPT.json` for the exact delivered DMG/ZIP hashes and structural checks. The native-Mac build script additionally invokes Apple codesign/hdiutil and real-Mac media tests when it is actually run. This Linux report does not claim those future checks passed.

## Native GitHub macOS evidence (subsequently completed)

The owner authorized publication to https://github.com/ahasnimsandu/ahas-compressor through GitHub CLI device sign-in.

- Native release run succeeded: https://github.com/ahasnimsandu/ahas-compressor/actions/runs/38960178824
- Built on an actual GitHub macOS runner; the bundled **arm64** Python runtime was executed and its ctypes/lzma/sqlite3 imports passed.
- **All 61 tests passed on macOS**, including actual `sips` image conversion and `avconvert` preset enumeration. This is not a test of every video codec or an actual video transcode.
- Apple's `codesign --verify --deep --strict` reported the app valid on disk and satisfying its designated requirement. This validates the ad-hoc signature, not Developer ID trust or notarization.
- Apple's `hdiutil verify` verified the native-built DMG and partition checksums.
- Release assets: https://github.com/ahasnimsandu/ahas-compressor/releases/tag/v2.0.0
- Cross-platform CI succeeded on Linux/macOS with Python 3.11/3.13, plus Chromium browser tests: https://github.com/ahasnimsandu/ahas-compressor/actions/runs/38960175273

These later native-run results supersede the initial Linux-only limitations for the specific checks listed above. Native file-dialog interactions, full GUI automation, actual video transcoding, macOS 11 compatibility, and Gatekeeper/quarantine approval are not claimed tested by this build run. A separate packaged-app launch/backend smoke workflow is provided; consult its result before treating that extra check as passed.
