#!/bin/sh
# Prepare a release: "## Unreleased" in CHANGELOG.md becomes "## X.Y.Z — today", the version goes into the
# package and the PKGBUILD, the checks run, then a commit and an annotated tag. Pushing the tag publishes the
# release on GitHub (.github/workflows/release.yml). Nothing is pushed from here.
# Usage: scripts/release.sh 0.5.0
set -eu
cd "$(dirname "$0")/.."
v="${1:?usage: scripts/release.sh X.Y.Z}"
echo "$v" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "not a version: $v" >&2; exit 2; }
[ -z "$(git status --porcelain)" ] || { echo "commit or stash your changes first" >&2; exit 1; }
if git rev-parse -q --verify "refs/tags/v$v" >/dev/null; then echo "v$v already exists" >&2; exit 1; fi
if grep -q '^## Unreleased' CHANGELOG.md; then
  sed -i "s/^## Unreleased.*/## $v — $(date +%F)/" CHANGELOG.md
fi
python3 scripts/release-notes.py "$v" >/dev/null
sed -i "s/^__version__ = .*/__version__ = \"$v\"/" compartir_selector/__init__.py
sed -i "s/^pkgver=.*/pkgver=$v/; s/^pkgrel=.*/pkgrel=1/" packaging/PKGBUILD
ruff check . && ruff format --check . && python3 -m pytest -q
git add CHANGELOG.md compartir_selector/__init__.py packaging/PKGBUILD
git diff --cached --quiet || git commit -q -m "Release $v"
git tag -a "v$v" -m "compartir-selector $v"
echo "v$v tagged. Publish it with: git push && git push origin v$v"
