#!/bin/sh
# Every check of the CI, in order. scripts/ci-container.sh runs it inside a fresh Arch with the tools installed; on
# a machine that has them it runs as is. It needs no token and no secret, so a compromised tool finds nothing to
# steal: the release's signing and publishing happen in another job that runs none of these tools.
set -eu
cd "$(dirname "$0")/.."
step() { printf '\n==> %s\n' "$*"; }

step "Secrets in every commit (gitleaks)"
gitleaks git --redact --no-banner .
step "Secrets in every commit, checked against their services (trufflehog)"
trufflehog git "file://$PWD" --results=verified,unknown --fail --no-update
step "Workflows (zizmor offline, actionlint with shellcheck, poutine)"
zizmor --offline .github/
actionlint
# No version check: it calls BoostSecurity (version-check.cicd.fun), which Harden-Runner blocks anyway.
POUTINE_DISABLE_VERSION_CHECK=1 poutine analyze_local . --fail-on-violation
step "Shell scripts (shellcheck)"
shellcheck scripts/*.sh tests/desktop/*.sh
step "Translations"
./scripts/update-locales.sh
step "Lint, formatting and the bandit security rules (ruff)"
ruff check .
ruff format --check .
step "Tests, property-based and security ones included (pytest)"
python -m pytest -q
step "Build sdist and wheel"
rm -rf dist
python -m build --no-isolation
