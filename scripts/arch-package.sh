#!/bin/sh
# The Arch package (.pkg.tar.zst) of the checked-out commit: makepkg runs packaging/PKGBUILD (build, check, package)
# exactly as a user does, except that the source is `git archive` of HEAD instead of GitHub's tarball of the tag,
# which does not exist yet while the release is being built (same files: GitHub makes it with git archive).
# makepkg refuses to run as root: as root (the CI container) this installs base-devel and the PKGBUILD's
# dependencies, then builds as an unprivileged user; as anyone else those must already be installed.
# Usage: scripts/arch-package.sh OUT_DIR
set -eu
cd "$(dirname "$0")/.."
out="${1:?usage: scripts/arch-package.sh OUT_DIR}"
mkdir -p "$out"
name=wlr-share-picker
version="$(sed -n 's/^pkgver=//p' packaging/PKGBUILD)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git archive --format=tar.gz --prefix="$name-$version/" -o "$work/$name-$version.tar.gz" HEAD
sum="$(sha256sum "$work/$name-$version.tar.gz" | cut -d' ' -f1)"
sed "s/^sha256sums=.*/sha256sums=('$sum')/" packaging/PKGBUILD > "$work/PKGBUILD"
# Timestamps from the commit, not from the build, so that rebuilding the same commit gives the same files.
build="cd '$work' && SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) makepkg --cleanbuild --noconfirm --noprogressbar"
if [ "$(id -u)" = 0 ]; then
  id builder >/dev/null 2>&1 || useradd --create-home builder
  chown -R builder "$work"
  deps="$(su builder -c "cd '$work' && makepkg --printsrcinfo" | awk '$1 ~ /^(make|check)?depends$/ {print $3}')"
  # shellcheck disable=SC2086 # one word per package
  pacman -S --needed --noconfirm --noprogressbar base-devel $deps >"$work/pacman.log" 2>&1 ||
    { cat "$work/pacman.log" >&2; exit 1; }
  su builder -c "$build"
else
  sh -c "$build"
fi
cp "$work"/*.pkg.tar.zst "$out/"
ls -l "$out"/*.pkg.tar.zst
