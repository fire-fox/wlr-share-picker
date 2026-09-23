#!/bin/sh
# A basic Wayland desktop with nothing on screen but two test windows: headless sway (software rendering, no GPU),
# PipeWire, xdg-desktop-portal and xdg-desktop-portal-wlr with the picker as its chooser. Then tests/desktop/e2e.py
# asks for the screen through the portal like any app would. Run as a regular user inside `dbus-run-session`, with
# XDG_RUNTIME_DIR set (scripts/ci-container.sh desktop does all of that). Logs and a screenshot go to OUT_DIR.
# Usage: dbus-run-session -- tests/desktop/session.sh OUT_DIR
set -eu
cd "$(dirname "$0")/../.."
out="${1:?usage: tests/desktop/session.sh OUT_DIR}"
mkdir -p "$out"
repo="$PWD"
export XDG_CURRENT_DESKTOP=sway WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 GSK_RENDERER=cairo
config="$(mktemp -d)"
export XDG_CONFIG_HOME="$config"
mkdir -p "$config/xdg-desktop-portal-wlr" "$config/xdg-desktop-portal"
printf '[screencast]\nchooser_type=dmenu\nchooser_cmd=%s/wlr-share-picker\n' "$repo" > "$config/xdg-desktop-portal-wlr/config"
printf '[preferred]\ndefault=none\norg.freedesktop.impl.portal.ScreenCast=wlr\norg.freedesktop.impl.portal.Screenshot=wlr\n' \
  > "$config/xdg-desktop-portal/portals.conf"
printf 'output HEADLESS-1 resolution 1280x720\n' > "$config/sway"

pids=""
cleanup() { for pid in $pids; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
pipewire > "$out/pipewire.log" 2>&1 & pids="$pids $!"
sleep 0.5
wireplumber > "$out/wireplumber.log" 2>&1 & pids="$pids $!"
sway -c "$config/sway" > "$out/sway.log" 2>&1 & pids="$pids $!"
WAYLAND_DISPLAY="" SWAYSOCK=""
for _ in $(seq 100); do  # sway's Wayland socket and IPC socket
  for socket in "$XDG_RUNTIME_DIR"/wayland-?; do [ -S "$socket" ] && WAYLAND_DISPLAY="${socket##*/}"; done
  for socket in "$XDG_RUNTIME_DIR"/sway-ipc.*.sock; do [ -S "$socket" ] && SWAYSOCK="$socket"; done
  [ -n "$WAYLAND_DISPLAY" ] && [ -n "$SWAYSOCK" ] && break
  sleep 0.1
done
[ -n "$WAYLAND_DISPLAY" ] && [ -n "$SWAYSOCK" ] || { echo "sway did not start:" >&2; cat "$out/sway.log" >&2; exit 1; }
export WAYLAND_DISPLAY SWAYSOCK
# Whatever D-Bus starts on demand from here on gets this desktop's environment too.
dbus-update-activation-environment WAYLAND_DISPLAY SWAYSOCK XDG_CURRENT_DESKTOP XDG_CONFIG_HOME GSK_RENDERER
WLR_SHARE_PICKER_DEBUG=1 /usr/lib/xdg-desktop-portal-wlr -l INFO > "$out/portal.log" 2>&1 &
backend=$!
pids="$pids $backend"
owned() {  # NameHasOwner never activates anything (a call to the name itself would start it on demand)
  case "$(gdbus call --session -d org.freedesktop.DBus -o /org/freedesktop/DBus -m org.freedesktop.DBus.NameHasOwner \
    "$1" 2>/dev/null)" in *true*) return 0 ;; esac
  return 1
}
wait_owned() { for _ in $(seq 150); do owned "$1" && return 0; sleep 0.1; done; echo "nobody took $1" >&2; exit 1; }
# The portal looks for its backends once, when it starts: the wlr one must be on the bus first.
wait_owned org.freedesktop.impl.portal.desktop.wlr
/usr/lib/xdg-desktop-portal -v > "$out/xdg-desktop-portal.log" 2>&1 & pids="$pids $!"
wait_owned org.freedesktop.portal.Desktop
ready=""
for _ in $(seq 150); do  # ScreenCast appears once the portal has checked that the wlr backend answers
  # No pipe into `grep -q`: its early exit would cut the very call that is activating the portal.
  interfaces="$(gdbus introspect --session -d org.freedesktop.portal.Desktop -o /org/freedesktop/portal/desktop \
    2>"$out/introspect.err" || true)"
  case "$interfaces" in *"interface org.freedesktop.portal.ScreenCast "*) ready=1; break ;; esac
  sleep 0.1
done
if [ -z "$ready" ]; then
  echo "the portal never offered ScreenCast; it offers:" >&2
  printf '%s\n' "$interfaces" | grep -o 'interface org.freedesktop.portal.[A-Za-z]*' >&2 || echo "(nothing: not running)" >&2
  cat "$out/introspect.err" >&2
  busctl --user list 2>/dev/null | grep -i portal >&2 || true
  if kill -0 "$backend" 2>/dev/null; then echo "xdg-desktop-portal-wlr is running" >&2; else
    echo "xdg-desktop-portal-wlr exited:" >&2; cat "$out/portal.log" >&2; fi
  exit 1
fi
# The test windows start only now: a GTK app asks the portal for its settings on startup, and one started before
# the portal is up would have D-Bus launch a second portal that takes over the name without ScreenCast.
foot --app-id test-terminal --title "Test terminal" sh -c 'echo test; exec sleep infinity' > "$out/foot.log" 2>&1 &
pids="$pids $!"
python tests/desktop/window.py > "$out/window.log" 2>&1 & pids="$pids $!"
for _ in $(seq 150); do  # both mapped, each with its foreign toplevel id
  [ "$(swaymsg -t get_tree | grep -c '"foreign_toplevel_identifier"')" -ge 2 ] && break
  sleep 0.1
done
python tests/desktop/e2e.py "$out/portal.log" "$out"
