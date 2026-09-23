"""Configuration: defaults + `$XDG_CONFIG_HOME/compartir-selector/config.toml` (optional) + environment variables.

Variables: COMPARTIR_SELECTOR_CONFIG (toml path), COMPARTIR_SELECTOR_DEBUG=1, COMPARTIR_SELECTOR_FRONTEND=gtk|dmenu.
"""

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Literal, get_origin

from . import logs

log = logs.get("config")

Frontend = Literal["auto", "gtk", "dmenu"]


@dataclass(frozen=True)
class Config:
    frontend: Frontend = "auto"  # auto = GTK and, if it fails, dmenu
    fallback: bool = True  # allow falling back to a dmenu (fuzzel/wofi/bemenu/rofi) when GTK cannot start
    dmenu: list[str] = field(default_factory=list)  # custom dmenu command; empty = autodetect
    title: str = ""  # empty = translated default ("What do you want to share?")
    thumbnail_width: int = 320  # px; height is 5/8 of the width
    columns: int = 0  # 0 = derived from the monitor width
    max_columns: int = 6
    capture_timeout: float = 2.5  # seconds per thumbnail; a window already being shared hangs grim
    capture_threads: int = 4
    monitor_scale: float = 0.2
    window_scale: float = 0.35
    jpeg_quality: int = 70
    reuse_choice_seconds: float = 90  # same app asking again within this window gets the same answer; 0 = off
    remember_choice: bool = True  # preselect the source shared last time (stored in $XDG_STATE_HOME)
    refresh_seconds: float = 2.0  # re-capture thumbnails while the picker is open; 0 = single capture
    hide_app_ids: list[str] = field(default_factory=list)  # windows of these app ids never show up
    hide_titles: list[str] = field(default_factory=list)  # nor windows whose title contains one of these
    theme: str = "auto"  # auto (your GTK palette, else by colour scheme) | dark | light
    auto: dict[str, str] = field(
        default_factory=dict
    )  # requesting app → source answered without a dialog, e.g. rustdesk = "DP-1"
    show_requester: bool = True  # title says which app is asking, when it can be told
    colors: dict[str, str] = field(
        default_factory=dict
    )  # per-key overrides: background, text, muted, card, card_border, accent, accent_text, empty
    debug: bool = False

    def validate(self) -> "Config":
        if self.frontend not in ("auto", "gtk", "dmenu"):
            log.warning("invalid frontend %r, using auto", self.frontend)
            return replace(self, frontend="auto").validate()
        # Upper bounds too: absurd values (refresh_seconds = 1e308) would overflow GLib timers or size requests.
        return replace(
            self,
            thumbnail_width=min(1920, max(120, self.thumbnail_width)),
            columns=min(24, max(0, self.columns)),
            max_columns=min(24, max(1, self.max_columns)),
            capture_timeout=min(60.0, max(0.5, self.capture_timeout)),
            capture_threads=min(32, max(1, self.capture_threads)),
            monitor_scale=min(1.0, max(0.05, float(self.monitor_scale))),
            window_scale=min(1.0, max(0.05, float(self.window_scale))),
            jpeg_quality=min(100, max(1, self.jpeg_quality)),
            reuse_choice_seconds=min(86400.0, max(0.0, float(self.reuse_choice_seconds))),
            refresh_seconds=0.0 if float(self.refresh_seconds) <= 0 else min(3600.0, max(0.5, float(self.refresh_seconds))),
            theme=self.theme if self.theme in ("auto", "dark", "light") else "auto",
        )


_TYPES = {f.name: f.type for f in fields(Config)}


def _type_ok(value, annotation) -> bool:
    """Whether a toml value fits the field's annotation: bool, int, float (an int is fine too), str (also for
    Literal choices, which `validate` checks), list of strings or table of strings. `True` is an int in
    Python, so booleans are told apart first."""
    expected = get_origin(annotation) or annotation
    if expected is Literal:
        expected = str
    if expected is bool or isinstance(value, bool):
        return expected is bool and isinstance(value, bool)
    if expected is float:
        return isinstance(value, int | float)
    if expected is list:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if expected is dict:
        return isinstance(value, dict) and all(isinstance(v, str) for v in value.values())
    return isinstance(value, expected)


def default_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "compartir-selector" / "config.toml"


def load(path: Path | None = None, env: dict[str, str] | None = None) -> Config:
    """Never raises: a broken toml or an unknown key is reported and whatever is valid is used."""
    environ = os.environ if env is None else env
    path = path or Path(environ.get("COMPARTIR_SELECTOR_CONFIG") or default_path())
    values: dict = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as e:
            log.warning("config %s unreadable (%s), using defaults", path, e)
            data = {}
        known = {f.name for f in fields(Config)}
        for key, value in data.items():
            if key not in known:
                log.warning("config: unknown key %r in %s", key, path)
                continue
            if not _type_ok(value, _TYPES[key]):
                log.warning("config: %s = %r has the wrong type in %s, using the default", key, value, path)
                continue
            values[key] = value
    if environ.get("COMPARTIR_SELECTOR_DEBUG") == "1":
        values["debug"] = True
    if frontend := environ.get("COMPARTIR_SELECTOR_FRONTEND"):
        values["frontend"] = frontend
    try:
        cfg = Config(**values)
    except TypeError as e:
        log.warning("config with invalid types (%s), using defaults", e)
        cfg = Config()
    return cfg.validate()
