#!/bin/bash
# Run locally. Uses GitHub CLI authentication, never asks for a token in chat.
set -euo pipefail
cd "$(dirname "$0")"
command -v gh >/dev/null || { echo 'Install GitHub CLI from https://cli.github.com, then run this again.'; read -r -p 'Press Return… ' _; exit 1; }
command -v git >/dev/null || { echo 'Install Xcode Command Line Tools (git), then retry.'; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login
LOGIN="$(gh api user --jq .login)"
read -r -p 'Repository name [ahas-compressor]: ' REPO
REPO="${REPO:-ahas-compressor}"
case "$REPO" in *[!A-Za-z0-9._-]*|'') echo 'Invalid repository name.'; exit 1;; esac
read -r -p 'Visibility: type public to publish publicly; Return keeps it PRIVATE: ' VISIBILITY
[ "$VISIBILITY" = public ] || VISIBILITY=private
if gh repo view "$LOGIN/$REPO" >/dev/null 2>&1; then
 echo 'That repository already exists. Nothing was pushed. See docs/GITHUB.md for updating an existing repo.'; exit 1
fi
if [ ! -d .git ]; then git init -b main; fi
if git remote get-url origin >/dev/null 2>&1; then
 echo 'This checkout already has an origin. Nothing was pushed; inspect it before continuing.'; exit 1
fi
git add .
if ! git diff --cached --quiet; then
 git -c user.name="$LOGIN" -c user.email="$LOGIN@users.noreply.github.com" commit -m 'AHAS 2.0: solid .ahas archives, explicit lossy media mode, elegant Mac UI'
fi
echo "Creating $VISIBILITY repository $LOGIN/$REPO and pushing the source…"
gh repo create "$LOGIN/$REPO" --"$VISIBILITY" --source . --remote origin --push
read -r -p 'Start the macOS build and create GitHub Release v2.0.1? [y/N]: ' BUILD
if [ "$BUILD" = y ] || [ "$BUILD" = Y ]; then
 gh workflow run macos-release.yml --ref main -f tag=v2.0.1
 echo 'Build requested. GitHub Actions must be enabled. This can use your account Actions minutes.'
fi
gh repo view --web
read -r -p 'Finished. Press Return to close… ' _
