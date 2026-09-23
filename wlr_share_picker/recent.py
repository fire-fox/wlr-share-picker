"""Two memories of the last choice.

Short-lived, in $XDG_RUNTIME_DIR (gone at logout; off without it, see `paths`): so an app that asks the portal
twice in a row (Chromium: one session for its preview, another to actually share) gets the same answer without a
second dialog. Reused only
when fresh, when it was an actual choice (never a cancel), when its source is still in the list and when the
request comes from the same process that chose (so another app never inherits the answer; when the requester
cannot be told, only a choice made just as blind is reused).

Persistent, in $XDG_STATE_HOME: what was shared last time, to preselect it in the grid. Windows are matched by
toplevel id and, failing that (ids change across restarts), by app id.
"""

import contextlib
import time
from pathlib import Path

from . import logs, paths
from .config import Config
from .protocol import Source, parse_line

log = logs.get("recent")

FILE_NAME = "last-choice.json"


def _path() -> Path | None:
    directory = paths.runtime_dir()
    return directory / FILE_NAME if directory else None


def _state_path() -> Path | None:
    directory = paths.state_dir()
    return directory / FILE_NAME if directory else None


def _read(path: Path | None) -> dict | None:
    record = paths.read_json(path) if path else None
    return record if isinstance(record, dict) else None


def remember(choice: str, app_id: str = "", now: float | None = None, persistent: bool = True, requester_pid: int = 0) -> None:
    """Store the chosen line in the short-lived memory and, if enabled, in the persistent one. Never raises."""
    source = parse_line(choice)
    if source is None:
        return
    record = {
        "kind": source.kind,
        "id": source.id,
        "app_id": app_id,
        "time": now if now is not None else time.time(),
        "requester_pid": requester_pid,
    }
    for path in (_path(), _state_path()) if persistent else (_path(),):
        if path is None:
            continue
        try:
            paths.write_json(path, record)
        except OSError as e:
            log.debug("could not remember the choice in %s: %s", path, e)


def preferred(sources: list[Source], app_ids: dict[str, str]) -> int | None:
    """Index of the source shared last time: same monitor, same window id, or else same app id."""
    record = _read(_state_path())
    if not record:
        return None
    kind, ident, app_id = record.get("kind"), record.get("id"), record.get("app_id") or ""
    for i, s in enumerate(sources):
        if s.kind == kind and s.id == ident:
            return i
    if kind == "window" and app_id:
        for i, s in enumerate(sources):
            if not s.is_monitor and app_ids.get(s.id, "") == app_id:
                return i
    return None


def recall(sources: list[Source], cfg: Config, now: float | None = None, requester_pid: int = 0) -> Source | None:
    """The source to answer with automatically, or None when the memory is off, stale, made for another process
    or no longer applies. `requester_pid` 0 means unknown, and unknown only matches unknown: a choice made for a
    known app is never handed to a request whose origin could not be told (nor the other way round)."""
    if cfg.reuse_choice_seconds <= 0:
        return None
    record = _read(_path())
    try:
        kind, ident, when = record["kind"], record["id"], float(record["time"])  # type: ignore[index]
        chooser_pid = int(record.get("requester_pid") or 0)  # type: ignore[union-attr]
    except (KeyError, TypeError, ValueError, OverflowError):  # OverflowError: "requester_pid": Infinity
        return None
    age = (now if now is not None else time.time()) - when
    if not 0 <= age <= cfg.reuse_choice_seconds:
        return None
    if requester_pid != chooser_pid:
        log.debug("last choice was made for pid %d, now pid %d asks: not reusing", chooser_pid, requester_pid)
        return None
    for source in sources:
        if source.kind == kind and source.id == ident:
            log.info("reusing the choice made %.0fs ago: %s %r", age, source.kind, source.name)
            return source
    return None


def forget() -> None:
    if (path := _path()) is not None:
        with contextlib.suppress(OSError):
            path.unlink()
