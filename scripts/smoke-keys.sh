#!/bin/sh
# Keyboard smoke test against the real GTK picker: opens it with a source list, sends keys with wtype
# (virtual keyboard protocol; works on wlroots compositors) and prints what it answered. Needs a display.
# Usage: scripts/smoke-keys.sh sources.txt   (one portal line per row, e.g. from `mmsg get all-clients`)
set -u
cd "$(dirname "$0")/.." || exit 1
SOURCES="${1:?sources file}"
TMP="$(mktemp -d)"
printf 'reuse_choice_seconds = 0\nremember_choice = false\n' > "$TMP/config.toml"
run() {
  name="$1"; shift
  rm -rf "${XDG_RUNTIME_DIR:-/tmp}/wlr-share-picker"
  ./wlr-share-picker --config "$TMP/config.toml" < "$SOURCES" > "$TMP/out" 2> "$TMP/err" &
  pid=$!
  sleep 2.5
  sh -c "$*"
  sleep 1.5
  kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  printf '%-22s → [%s] %s\n' "$name" "$(head -c 70 "$TMP/out")" "$(grep -oE 'INFO: (answered|cancelled|signal).*' "$TMP/err" | head -1)"
}
run "digit 2"              "wtype 2"
run "Escape"               "wtype -k Escape"
run "Enter"                "wtype -k Return"
run "type roam + Enter"    "wtype roam; sleep 0.5; wtype -k Return"
run "Right + Enter"        "wtype -k Right; sleep 0.3; wtype -k Return"
run "type x + Esc + Enter" "wtype zzz; sleep 0.3; wtype -k Escape; sleep 0.3; wtype -k Return"
rm -rf "$TMP" "${XDG_RUNTIME_DIR:-/tmp}/wlr-share-picker"
