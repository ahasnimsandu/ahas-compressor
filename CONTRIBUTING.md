# Contributing to AHAS

Use Python 3.11+; application runtime dependencies are standard-library only. Run `python3 -m unittest discover -s tests -v`. Two real macOS media tests are intentionally skipped on non-Mac systems; mocked orchestration tests are not codec validation.

Optional browser tests use the pinned Playwright dev dependency: `npm install`, `npx playwright install chromium`, `npm run test:browser`. Screenshots can be regenerated with `SCREENSHOTS=1 npm run test:browser`.

For native packaging, use `bash macos/build-on-mac.sh` on macOS with Xcode Command Line Tools. Read the build/security notes before enabling public releases. Do not commit generated archives, app binaries, DMGs, user media, caches, or credentials.

Changes to the archive format must update `docs/FORMAT.md`, retain legacy reading tests, and include malformed-input/round-trip/cancellation tests. Compression changes should include reproducible benchmarks. Lossy behavior must remain opt-in and separate from lossless archiving.

Test real Mac startup, image/video conversions, cancellation, verification/restoration, and code-signing behavior before declaring a release supported. Minimum OS versions and media codecs require explicit validation, not assumptions from passing Linux tests.
