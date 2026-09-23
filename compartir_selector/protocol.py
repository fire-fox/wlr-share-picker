"""Contract with xdg-desktop-portal-wlr in `chooser_type=dmenu` mode.

Input on stdin, one source per line:
    Monitor: <name> <free-form description>
    Window: <title> (<id from ext-foreign-toplevel-list-v1>)
The id is opaque (hex on wlroots compositors): it is matched case-insensitively here but handed back verbatim
to grim and to the portal, which compare it byte for byte.
Output: the chosen line, byte for byte (including its newline). Nothing = cancel.

This module is pure (no GTK, no subprocesses) so it can be tested in isolation.
"""

import re
from dataclasses import dataclass
from typing import Literal

from . import logs

log = logs.get("protocol")

Kind = Literal["monitor", "window"]

_MONITOR = re.compile(r"^Monitor: (\S+)\s*(.*)$")
_WINDOW = re.compile(r"^Window: (.*) \(([^()\s]+)\)$")


@dataclass(frozen=True)
class Source:
    """One portal entry, already interpreted."""

    line: str  # original line exactly as received, newline included: this is what must be returned
    kind: Kind
    id: str  # output name (DP-1) or toplevel id, lowercased: the key for compositor data and the memories
    name: str  # monitor name or window title
    description: str = ""  # monitor description; for windows the compositor fills in the app id
    raw_id: str = ""  # toplevel id exactly as the portal sent it

    @property
    def is_monitor(self) -> bool:
        return self.kind == "monitor"

    def grim_args(self) -> list[str]:
        """How to ask grim for this source: `-o output` or `-T id`."""
        return ["-o", self.id] if self.is_monitor else ["-T", self.raw_id or self.id]


def parse_line(line: str) -> Source | None:
    text = line.rstrip("\r\n")
    if m := _MONITOR.match(text):
        return Source(line=line, kind="monitor", id=m.group(1), name=m.group(1), description=m.group(2).strip())
    if m := _WINDOW.match(text):
        return Source(line=line, kind="window", id=m.group(2).lower(), name=m.group(1), raw_id=m.group(2))
    return None


def parse(lines: list[str]) -> list[Source]:
    """Interpret every line; lines that break the contract are skipped with a warning (never fatal)."""
    sources = []
    for line in lines:
        if not line.strip():
            continue
        source = parse_line(line)
        if source is None:
            log.warning("unrecognised portal line, skipped: %r", line)
            continue
        sources.append(source)
    # Monitors first: there are few of them, they capture fast and they are usually what people want.
    sources.sort(key=lambda s: 0 if s.is_monitor else 1)
    return sources


def refresh_title(choice: str, titles: dict[str, str]) -> str:
    """The portal matches the answer against the window's *current* title, and titles change while the dialog
    is open (Teams counters, page loads). If the compositor reports a different title for the chosen window,
    rebuild the line with it; otherwise return the line untouched."""
    source = parse_line(choice)
    if source is None or source.is_monitor:
        return choice
    current = titles.get(source.id)
    if not current or current == source.name:
        return choice
    log.info("title of window %s changed while choosing: %r → %r", source.id, source.name, current)
    return f"Window: {current} ({source.raw_id or source.id})\n"


def exclude(sources: list[Source], app_ids: dict[str, str], hide_app_ids: list[str], hide_titles: list[str]) -> list[Source]:
    """Drop windows whose app id is listed or whose title contains a listed fragment (case-insensitive).
    `app_ids` maps toplevel id → app id. Monitors are never hidden. If everything would go, nothing is hidden."""
    hidden_ids = {a.casefold() for a in hide_app_ids}
    fragments = [t.casefold() for t in hide_titles if t]
    kept = []
    for s in sources:
        if not s.is_monitor:
            if app_ids.get(s.id, "").casefold() in hidden_ids:
                continue
            title = s.name.casefold()
            if any(f in title for f in fragments):
                continue
        kept.append(s)
    if not kept:
        log.warning("hide_app_ids/hide_titles would hide every source: ignoring them")
        return sources
    return kept
