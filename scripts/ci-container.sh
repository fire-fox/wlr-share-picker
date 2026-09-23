#!/bin/sh
# Run the CI (scripts/ci.sh) in a fresh, fully updated archlinux:latest container, the same way on GitHub and on
# your machine (podman or docker). The repository is mounted read-only and copied inside: your working tree is not
# touched. Tools Arch does not package come from scripts/ci-tools.sh, verified with Sigstore. The container gets no
# token: with GH_TOKEN set (read-only), zizmor's online audits run in a separate container that holds nothing else.
# Usage: scripts/ci-container.sh checks [OUT_DIR]   every check; OUT_DIR also receives the release files
#        scripts/ci-container.sh mutation OUT_DIR   weekly mutation testing (scripts/mutation.sh), report in OUT_DIR
set -eu
cd "$(dirname "$0")/.."
engine="$(command -v podman || command -v docker)"
image="docker.io/library/archlinux:latest"
base="git python python-gobject gtk4 gtk4-layer-shell grim gettext python-pytest python-hypothesis"
mode="${1:?usage: scripts/ci-container.sh checks [OUT_DIR] | mutation OUT_DIR}"
out="${2:-}"
case "$mode" in
  checks)
    packages="$base python-build python-installer python-setuptools python-wheel ruff gitleaks zizmor actionlint \
shellcheck cosign syft"
    commands="scripts/ci-tools.sh /usr/local/bin && scripts/ci.sh && if [ -d /out ]; then scripts/release-files.sh /out; fi" ;;
  mutation)
    packages="$base python-pip"
    commands="scripts/mutation.sh /out" ;;
  *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac

if [ "$mode" = checks ] && [ -n "${GH_TOKEN:-}" ]; then
  printf '==> Workflows, online audits: impostor commits, known-vulnerable actions (zizmor)\n'
  "$engine" run --rm -e GH_TOKEN -v "$PWD/.github:/src/.github:ro,Z" "$image" sh -euc '
    pacman -Syu --noconfirm --needed --noprogressbar zizmor >/tmp/pacman.log 2>&1 || { cat /tmp/pacman.log; exit 1; }
    zizmor /src/.github/'
fi

set -- -v "$PWD:/src:ro,Z"
if [ -n "$out" ]; then
  mkdir -p "$out"
  set -- "$@" -v "$(realpath "$out"):/out:Z"
fi
"$engine" run --rm "$@" "$image" sh -euc "
  pacman -Syu --noconfirm --needed --noprogressbar $packages >/tmp/pacman.log 2>&1 || { cat /tmp/pacman.log; exit 1; }
  cp -a /src /w
  cd /w
  git config --global --add safe.directory /w
  $commands"
