# Publish this repository to GitHub

Upstream: https://github.com/ahasnimsandu/ahas-compressor

The owner authorized publication through official GitHub CLI device sign-in. Source and native-Mac release workflows are included. The instructions below publish a new copy under your own account; do not overwrite upstream unless you are its authorized owner.

## Guided publishing on your Mac

1. Install GitHub CLI from https://cli.github.com and Xcode Command Line Tools if needed (`xcode-select --install`).
2. Extract the source ZIP and keep the folder together.
3. Inspect and double-click `Publish to GitHub.command`, or run `bash "Publish to GitHub.command"` from this folder.
4. The script uses `gh auth login` to authenticate directly with GitHub. Never paste a password or token into a chat.
5. Choose a repository name and visibility. **Private is the default.** It refuses to overwrite an existing repository or reuse an unexpected origin.
6. It commits and pushes the source. It can optionally request the native Mac build and create Release `v2.0.0`. Actions must be enabled; private-repository builds can use paid Actions minutes depending on your account.

## Manual commands

After authenticating and configuring your Git identity, run from the source folder:

```sh
git init -b main
git add .
git commit -m "AHAS 2.0"
gh auth login
gh repo create ahas-compressor --private --source . --remote origin --push
# Use --public instead only if you want a public repository.
gh workflow run macos-release.yml --ref main -f tag=v2.0.0
gh run list
```

The workflow builds on a macOS runner, runs the real macOS image/preset tests, uses Apple's `codesign` and `hdiutil`, and uploads a DMG, ZIP, and checksum file to the release. It is still ad-hoc signed, not Developer ID signed or notarized. It does not automate a full GUI launch/restore test.

To update an existing repository, inspect `git remote -v`, set the correct existing remote yourself, commit your changes, and push the intended branch. The guided script deliberately does not force-push or overwrite an existing remote/repository.

No credentials, local archives, DMGs, user media, or runtime binaries need to be committed. The pinned runtime is downloaded and checksum-checked by the build workflow. Screenshots, source, license documents, and tests are included.
