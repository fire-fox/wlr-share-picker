"""Window metadata (app id, title) the portal does not send: every compositor exposes it its own way.

Adding a compositor = a class with `name`, `available()` and `clients()`, appended to BACKENDS. Everything
degrades silently to `{}`: the picker works the same, just without icon or app name on the cards.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from . import logs

log = logs.get("compositor")

TIMEOUT = 2.0


@dataclass(frozen=True)
class Client:
    app_id: str
    title: str = ""


class Compositor(Protocol):
    name: str

    def available(self) -> bool: ...

    def clients(self) -> dict[str, Client]:
        """toplevel id (hex, lowercase) → Client."""
        ...


def _json(cmd: list[str]):
    # S603: fixed argument lists (mmsg / swaymsg), no shell and no outside input.
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=True)  # noqa: S603
    return json.loads(r.stdout)


class Mango:
    name = "mango"

    def available(self) -> bool:
        return bool(os.environ.get("MANGO_INSTANCE_SIGNATURE")) and shutil.which("mmsg") is not None

    def clients(self) -> dict[str, Client]:
        data = _json(["mmsg", "get", "all-clients"])
        items = data.get("clients", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return {}
        return {
            c["foreign_toplevel_id"].lower(): Client(app_id=c.get("appid") or "", title=c.get("title") or "")
            for c in items
            if isinstance(c, dict) and c.get("foreign_toplevel_id")
        }


class Sway:
    """sway ≥ 1.10 exposes `foreign_toplevel_identifier` in the tree; also works for compositors speaking its IPC."""

    name = "sway"

    def available(self) -> bool:
        return bool(os.environ.get("SWAYSOCK")) and shutil.which("swaymsg") is not None

    def clients(self) -> dict[str, Client]:
        result: dict[str, Client] = {}
        pending = [_json(["swaymsg", "-t", "get_tree"])]
        while pending:
            node = pending.pop()
            ident = node.get("foreign_toplevel_identifier")
            if ident:
                app_id = node.get("app_id") or (node.get("window_properties") or {}).get("class") or ""
                result[str(ident).lower()] = Client(app_id=app_id, title=node.get("name") or "")
            pending.extend(node.get("nodes", []) + node.get("floating_nodes", []))
        return result


class NoCompositor:
    name = "none"

    def available(self) -> bool:
        return True

    def clients(self) -> dict[str, Client]:
        return {}


BACKENDS: list[type] = [Mango, Sway, NoCompositor]


def detect() -> Compositor:
    """First backend available in this session (session variables + IPC binary); `NoCompositor` always is."""
    for cls in BACKENDS:
        backend = cls()
        if backend.available():
            log.debug("compositor detected: %s", backend.name)
            return backend
    return NoCompositor()


def safe_clients(compositor: Compositor) -> dict[str, Client]:
    """Never raises: any IPC failure leaves the cards without an app id, not the user without a picker."""
    try:
        result = compositor.clients()
        log.debug("%s: %d clients", compositor.name, len(result))
        return result
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as e:
        log.warning("could not read clients from %s: %s", compositor.name, e)
        return {}
