"""Who is asking for the screen. The portal never tells the chooser, but it leaves a trail that any process of
the same user can follow, with no patches to the portal:

  1. every screencast session is a D-Bus object under /org/freedesktop/portal/desktop/session/<sender>/<token>,
     already present when the chooser runs;
  2. org.freedesktop.DBus.GetConnectionUnixProcessID turns <sender> into a PID;
  3. the PID's cgroup names the systemd scope the app was launched in, `app-<desktop id>-<pid>.scope`, the
     freedesktop convention for placing applications in systemd (Chromium → org.chromium.Chromium). Apps
     started outside that convention (a terminal) fall back to the process name.

Sessions of apps already sharing are also alive, so the paths seen on each run are stored in the runtime
directory (`paths.runtime_dir`) and the requester is whichever session is new. Everything degrades to "unknown" and the dialog.
"""

import contextlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import logs, paths

log = logs.get("requester")

SESSIONS_ROOT = "/org/freedesktop/portal/desktop/session"
SEEN_FILE = "sessions-seen.json"
LAUNCHER_PREFIXES = ("flatpak", "gnome", "kde", "plasma", "dbus", "uwsm", "systemd")
_SCOPE = re.compile(r"app-(?P<body>.+?)(?:-\d+)?(?:@[^.]*)?\.(?:scope|service)$")


@dataclass(frozen=True)
class Requester:
    app_id: str  # desktop id from the systemd scope, else the process name
    comm: str  # process name (/proc/<pid>/comm)
    pid: int
    path: str  # session object path

    def matches(self, key: str) -> bool:
        """Config keys can be the desktop id, its last segment (Chromium for org.chromium.Chromium) or the process name."""
        k = key.casefold()
        return k in {self.app_id.casefold(), self.comm.casefold(), self.app_id.rsplit(".", 1)[-1].casefold()}


def app_id_from_cgroup(text: str) -> str | None:
    """Desktop id from the contents of /proc/<pid>/cgroup, or None when the process is not in an app scope."""
    for line in text.splitlines():
        unit = line.rsplit("/", 1)[-1]
        m = _SCOPE.match(unit)
        if not m:
            continue
        body = m.group("body").replace("\\x2d", "-")
        for prefix in LAUNCHER_PREFIXES:
            if body.startswith(prefix + "-") and len(body) > len(prefix) + 1:
                body = body[len(prefix) + 1 :]
                break
        return body or None
    return None


def _seen_path() -> Path | None:
    directory = paths.runtime_dir()
    return directory / SEEN_FILE if directory else None


def _load_seen() -> set[str]:
    path = _seen_path()
    data = paths.read_json(path) if path else None
    return {p for p in data if isinstance(p, str)} if isinstance(data, list) else set()


def _store_seen(sessions: list[str]) -> None:
    path = _seen_path()
    if path is None:
        return
    try:
        paths.write_json(path, sorted(sessions))
    except OSError as e:
        log.debug("could not store the sessions seen: %s", e)


def _introspect(bus, path: str) -> list[str]:
    from gi.repository import GLib

    reply = bus.call_sync(
        "org.freedesktop.portal.Desktop",
        path,
        "org.freedesktop.DBus.Introspectable",
        "Introspect",
        None,
        GLib.VariantType("(s)"),
        0,
        1000,
        None,
    )
    # S314: the XML is the portal's D-Bus introspection, a session service; the bundled expat (≥ 2.4) caps entity
    # expansion, which is what defusedxml guards against.
    tree = ET.fromstring(reply.unpack()[0])  # noqa: S314
    return [node.get("name") for node in tree.findall("node") if node.get("name")]


def live_sessions(bus) -> list[str]:
    """Object paths of every screencast session currently alive in the portal."""
    paths = []
    for sender in _introspect(bus, SESSIONS_ROOT):
        for token in _introspect(bus, f"{SESSIONS_ROOT}/{sender}"):
            paths.append(f"{SESSIONS_ROOT}/{sender}/{token}")
    return paths


def pid_of(bus, sender_segment: str) -> int:
    """`1_328` (path segment) → `:1.328` (bus name) → PID."""
    from gi.repository import GLib

    name = ":" + sender_segment.replace("_", ".")
    reply = bus.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "GetConnectionUnixProcessID",
        GLib.Variant("(s)", (name,)),
        GLib.VariantType("(u)"),
        0,
        1000,
        None,
    )
    return int(reply.unpack()[0])


def describe(pid: int, path: str, proc: Path = Path("/proc")) -> Requester:
    comm = ""
    app_id = None
    with contextlib.suppress(OSError):
        comm = (proc / str(pid) / "comm").read_text(encoding="utf-8").strip()
    with contextlib.suppress(OSError):
        app_id = app_id_from_cgroup((proc / str(pid) / "cgroup").read_text(encoding="utf-8"))
    return Requester(app_id=app_id or comm, comm=comm, pid=pid, path=path)


def session_bus():
    from gi.repository import Gio

    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def detect(
    sessions: Callable[[object], list[str]] = live_sessions,
    pid_lookup: Callable[[object, str], int] = pid_of,
    proc: Path = Path("/proc"),
    connect: Callable[[], object] = session_bus,
) -> list[Requester]:
    """The apps whose session is new since the last run (or every live one if nothing is new). Never raises."""
    try:
        bus = connect()
        paths = sessions(bus)
    except Exception as e:  # noqa: BLE001
        log.debug("could not list portal sessions: %s", e)
        return []
    seen = _load_seen()
    _store_seen(paths)
    candidates = [p for p in paths if p not in seen] or paths
    result: list[Requester] = []
    for path in candidates:
        try:
            pid = pid_lookup(bus, path.removeprefix(SESSIONS_ROOT + "/").split("/", 1)[0])
        except Exception as e:  # noqa: BLE001
            log.debug("no PID for %s: %s", path, e)
            continue
        if any(r.pid == pid for r in result):
            continue
        result.append(describe(pid, path, proc))
    log.debug("requesters: %s", [(r.app_id, r.pid) for r in result])
    return result


def auto_choice(requesters: list[Requester], sources, app_ids: dict[str, str], rules: dict[str, str]):
    """The source an `[auto]` rule picks for the requester, or None. A rule value names a monitor (DP-1) or a
    window's app id (the first window of that app wins). Only with exactly one requester: when it cannot be
    told which app is asking, a rule for one of them must not hand the screen to another without a dialog."""
    if len(requesters) != 1:
        if rules and requesters:
            log.info("[auto] not applied: cannot tell which of %s is asking", ", ".join(r.app_id for r in requesters))
        return None
    for key, target in rules.items():
        if not any(r.matches(key) for r in requesters):
            continue
        for s in sources:
            if s.is_monitor and s.id.casefold() == target.casefold():
                return s
        for s in sources:
            if not s.is_monitor and app_ids.get(s.id, "").casefold() == target.casefold():
                return s
        log.warning("[auto] %s = %r: no such monitor or window right now, showing the dialog", key, target)
    return None
