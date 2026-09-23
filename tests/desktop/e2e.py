"""End to end on a real (headless) Wayland desktop: an app asks the real portal for the screen, the portal runs the
picker, virtual key presses choose, and the portal must hand out a PipeWire stream of the chosen kind.

Run by tests/desktop/session.sh, which starts sway, PipeWire, xdg-desktop-portal and xdg-desktop-portal-wlr (pointed
at the picker) inside a D-Bus session, with two test windows open. Exit status 0 = every case passed.
Usage: python tests/desktop/e2e.py PORTAL_LOG OUT_DIR
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from gi.repository import Gio, GLib

DESKTOP = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"
MONITOR, WINDOW = 1, 2  # source types, as the portal reports them on each stream
PICKER = str(Path(__file__).resolve().parents[2] / "compartir-selector")  # the portal's chooser_cmd, for pgrep -f
CANCELLED = 1


class Portal:
    """Just enough of the ScreenCast portal client, the way Chromium or OBS use it."""

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.count = 0

    def _request(self, method: str, args: list, options: dict, timeout: int = 60) -> tuple:
        self.count += 1
        token = f"e2e{self.count}"
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        loop = GLib.MainLoop()
        result: dict = {}

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            result["code"], result["results"] = params.unpack()
            loop.quit()

        def on_timeout():
            result.setdefault("code", "timeout")
            loop.quit()
            return GLib.SOURCE_REMOVE

        subscription = self.bus.signal_subscribe(
            DESKTOP, "org.freedesktop.portal.Request", "Response", path, None, 0, on_response
        )
        signature = "(" + "".join(sig for sig, _ in args) + "a{sv})"
        values = (*(value for _, value in args), {"handle_token": GLib.Variant("s", token), **options})
        self.bus.call_sync(DESKTOP, OBJECT, SCREENCAST, method, GLib.Variant(signature, values), None, 0, -1, None)
        timer = GLib.timeout_add_seconds(timeout, on_timeout)
        loop.run()
        if result["code"] != "timeout":
            GLib.source_remove(timer)
        self.bus.signal_unsubscribe(subscription)
        return result["code"], result.get("results", {})

    def create(self) -> str:
        code, results = self._request("CreateSession", [], {"session_handle_token": GLib.Variant("s", f"s{self.count}")})
        assert code == 0, f"CreateSession answered {code}"
        return results["session_handle"]

    def select(self, session: str) -> int:
        options = {"types": GLib.Variant("u", MONITOR | WINDOW), "multiple": GLib.Variant("b", False)}
        return self._request("SelectSources", [("o", session)], options)[0]

    def start(self, session: str) -> tuple:
        return self._request("Start", [("o", session), ("s", "")], {})

    def close(self, session: str) -> None:
        """Close the session; after a cancel the portal has closed it already."""
        try:
            self.bus.call_sync(DESKTOP, session, "org.freedesktop.portal.Session", "Close", None, None, 0, -1, None)
        except GLib.Error as e:
            if "does not exist" not in e.message:
                raise


def picker_running() -> bool:
    return subprocess.run(["pgrep", "-f", PICKER], capture_output=True).returncode == 0


MAPPED = "picker mapped with"  # the picker's own debug line once its window is on screen


def press_when_shown(keys: list[str], log: Path, mapped_before: int, screenshot: Path | None, done: threading.Event):
    """Wait until the picker says its window is mapped, let the thumbnails arrive, then press; press again while it
    is still up (a press can land before the layer has keyboard focus)."""
    deadline = time.monotonic() + 60
    while log.read_text(errors="replace").count(MAPPED) <= mapped_before and not done.is_set():
        if time.monotonic() > deadline:
            return
        time.sleep(0.1)
    time.sleep(1.5)
    if screenshot is not None and picker_running():
        subprocess.run(["grim", "-o", "HEADLESS-1", str(screenshot)], check=False)
    with open(log.parent / "wtype.log", "a") as errors:
        for _ in range(10):
            if done.is_set() or not picker_running():
                return
            errors.write(f"{time.strftime('%T')} pressing {keys}\n")
            errors.flush()
            # Each wtype brings a new virtual keyboard, and sway moves the keyboard focus away and back when one
            # appears: -s 400 waits for the focus to return before typing, or the key lands in the gap.
            subprocess.run(["wtype", "-s", "400", *keys], check=False, stderr=errors)
            time.sleep(1)


def ask(portal: Portal, log: Path, keys: list[str] | None, screenshot: Path | None = None) -> tuple:
    """One full request: (SelectSources code, stream source type or None, seconds the answer took)."""
    session = portal.create()
    done = threading.Event()
    mapped_before = log.read_text(errors="replace").count(MAPPED)
    presser = (
        threading.Thread(target=press_when_shown, args=(keys, log, mapped_before, screenshot, done), daemon=True)
        if keys
        else None
    )
    if presser:
        presser.start()
    began = time.monotonic()
    code = portal.select(session)
    took = time.monotonic() - began
    done.set()
    source_type = None
    if code == 0:
        start_code, results = portal.start(session)
        assert start_code == 0, f"Start answered {start_code}"
        streams = results.get("streams", [])
        assert streams, "Start returned no stream"
        node, props = streams[0]
        assert node > 0, f"bad PipeWire node {node}"
        source_type = props.get("source_type")
    portal.close(session)
    time.sleep(0.5)
    return code, source_type, took


def main() -> int:
    log, out = Path(sys.argv[1]), Path(sys.argv[2])
    memory = Path(os.environ["XDG_RUNTIME_DIR"]) / "compartir-selector" / "last-choice.json"
    portal = Portal()
    failures = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
        if not ok:
            failures.append(name)

    code, kind, _ = ask(portal, log, ["-k", "Escape"])
    check("Esc cancels", code == CANCELLED and kind is None, f"SelectSources {code}")

    code, kind, _ = ask(portal, log, ["2"], screenshot=out / "picker.png")
    check("2 shares the first window", code == 0 and kind == WINDOW, f"SelectSources {code}, stream type {kind}")

    code, kind, took = ask(portal, log, None)
    check(
        "the same app asking again gets it without a dialog",
        code == 0 and kind == WINDOW and took < 10,
        f"SelectSources {code}, stream type {kind}, {took:.1f}s",
    )

    memory.unlink(missing_ok=True)
    code, kind, _ = ask(portal, log, ["1"])
    check("1 shares the monitor", code == 0 and kind == MONITOR, f"SelectSources {code}, stream type {kind}")

    text = log.read_text(errors="replace")
    check(
        "the portal ran the picker four times",
        text.count("INFO: asked for 1 monitor(s) and 2 window(s)") == 4,
        "picker log lines",
    )
    check("the sway backend named the windows", "sway: 2 clients" in text, "compositor IPC")
    check(
        "the requester was found through D-Bus", "requesters: [(" in text and "requesters: []" not in text, "portal session → PID"
    )
    check("every thumbnail was captured", "grim failed" not in text and "grim exceeded" not in text, "grim -o / -T")
    print(f"\n{len(failures)} failed" if failures else "\nall passed", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
