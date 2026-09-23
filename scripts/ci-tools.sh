#!/bin/sh
# Install the CI tools Arch does not package (trufflehog, grype, poutine), always their latest release, each one
# verified with Sigstore before it can run: cosign checks that the release's checksums file was signed by that
# project's own release workflow on GitHub, then the archive's checksum is checked against it.
# A moved tag or a swapped asset fails here instead of running. Needs curl, cosign, sha256sum and tar.
# Usage: scripts/ci-tools.sh DESTINATION_DIR
set -eu
dest="${1:?usage: scripts/ci-tools.sh DESTINATION_DIR}"
mkdir -p "$dest"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
issuer="https://token.actions.githubusercontent.com"

latest() {  # repo → tag of its latest release (the redirect of /releases/latest, no API rate limit)
  curl -fsSI "https://github.com/$1/releases/latest" | sed -n 's|^[Ll]ocation: .*/tag/||p' | tr -d '\r'
}

fetch() {  # repo tag asset…
  repo=$1 tag=$2
  shift 2
  for asset in "$@"; do
    curl -fsSL --retry 3 -o "$work/$asset" "https://github.com/$repo/releases/download/$tag/$asset"
  done
}

checked() {  # checksums-file archive: the archive's line in the (already verified) checksums file must match
  (cd "$work" && grep -E "[[:space:]]\*?$2\$" "$1" | sha256sum -c --status -) || { echo "checksum mismatch: $2" >&2; exit 1; }
}

# checksums file signed with a certificate + signature (.pem / .sig), goreleaser style
signed_checksums() {  # repo name workflow-identity
  repo=$1 name=$2 identity=$3
  tag=$(latest "$repo")
  version=${tag#v}
  sums="${name}_${version}_checksums.txt"
  archive="${name}_${version}_linux_amd64.tar.gz"
  fetch "$repo" "$tag" "$sums" "$sums.pem" "$sums.sig" "$archive"
  cosign verify-blob --certificate "$work/$sums.pem" --signature "$work/$sums.sig" \
    --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$work/$sums" 2>/dev/null
  checked "$sums" "$archive"
  tar -xzf "$work/$archive" -C "$work" "$name"
  install -m 755 "$work/$name" "$dest/$name"
  echo "$name $tag: signature and checksum verified"
}

signed_checksums trufflesecurity/trufflehog trufflehog \
  '^https://github\.com/trufflesecurity/trufflehog/\.github/workflows/release\.yml@refs/tags/v'
signed_checksums anchore/grype grype \
  '^https://github\.com/anchore/grype/\.github/workflows/release\.yaml@refs/heads/main$'

# poutine: checksums file with a Sigstore bundle
tag=$(latest boostsecurityio/poutine)
sums="poutine_${tag#v}_checksums.txt"
fetch boostsecurityio/poutine "$tag" "$sums" "$sums.sigstore.json" poutine_Linux_x86_64.tar.gz
cosign verify-blob --bundle "$work/$sums.sigstore.json" --certificate-oidc-issuer "$issuer" \
  --certificate-identity-regexp '^https://github\.com/boostsecurityio/poutine/\.github/workflows/release\.yml@refs/tags/v' \
  "$work/$sums" 2>/dev/null
checked "$sums" poutine_Linux_x86_64.tar.gz
tar -xzf "$work/poutine_Linux_x86_64.tar.gz" -C "$work" poutine
install -m 755 "$work/poutine" "$dest/poutine"
echo "poutine $tag: signature and checksum verified"
