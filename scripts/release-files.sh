#!/bin/sh
# Release files from a checked build (run after scripts/ci.sh, which leaves dist/): the wheel and sdist, an SPDX SBOM
# of the package, an SPDX SBOM of the build environment (every Arch package it was built and tested with, gtk4 and
# gtk4-layer-shell included) and grype's report of known vulnerabilities in that environment. Signing happens later,
# in the publish job. Needs syft, grype and python-installer.
# Usage: scripts/release-files.sh OUT_DIR
set -eu
cd "$(dirname "$0")/.."
out="${1:?usage: scripts/release-files.sh OUT_DIR}"
mkdir -p "$out"
cp dist/* "$out/"
installed="$(mktemp -d)"
trap 'rm -rf "$installed"' EXIT
python -m installer --destdir "$installed" dist/*.whl
version="$(python -c 'import wlr_share_picker as c; print(c.__version__)')"
syft scan "dir:$installed" --source-name wlr-share-picker --source-version "$version" \
  -o "spdx-json=$out/wlr-share-picker.spdx.json"
# The Arch package database of this container (the `alpm` catalogers), nothing else: pseudo-filesystems and the
# mounts stay out, and so does the list of every file each package owns (packages only: ~1 MB instead of ~20 MB).
SYFT_FILE_METADATA_SELECTION=none SYFT_RELATIONSHIPS_PACKAGE_FILE_OWNERSHIP=false \
  syft scan dir:/ --select-catalogers alpm --source-name archlinux-build-environment --source-version "$(date -u +%F)" \
  -o "spdx-json=$out/build-environment.spdx.json" \
  --exclude './proc/**' --exclude './sys/**' --exclude './dev/**' --exclude './src/**' --exclude './w/**' \
  --exclude './out/**' --exclude './tmp/**'
grype "sbom:$out/build-environment.spdx.json" -o table > "$out/build-environment-vulnerabilities.txt"
for f in wlr-share-picker.spdx.json build-environment.spdx.json; do
  test -s "$out/$f" || { echo "empty SBOM: $f" >&2; exit 1; }
done
echo "release files in $out:"
ls -l "$out"
