#!/bin/sh
# Root side of the desktop test, inside the fresh Arch of `scripts/ci-container.sh desktop`: a regular user with a
# private runtime directory runs tests/desktop/session.sh in a D-Bus session; its logs and screenshot end in OUT_DIR.
# sway ships with the cap_sys_nice file capability, which containers do not grant (exec would fail with EPERM);
# a headless sway does not need it, so it is dropped here, inside the throwaway container only.
# Usage: tests/desktop/container.sh OUT_DIR
set -eu
cd "$(dirname "$0")/../.."
out="${1:?usage: tests/desktop/container.sh OUT_DIR}"
setcap -r "$(command -v sway)" 2>/dev/null || true
useradd --create-home tester
install -d -m 700 -o tester -g tester /tmp/runtime-tester
cp -a . /home/tester/repo
chown -R tester:tester /home/tester/repo
status=0
su tester -c 'cd ~/repo && XDG_RUNTIME_DIR=/tmp/runtime-tester dbus-run-session -- tests/desktop/session.sh /tmp/desktop' || status=$?
mkdir -p "$out"
cp -a /tmp/desktop/. "$out/" 2>/dev/null || true
exit "$status"
