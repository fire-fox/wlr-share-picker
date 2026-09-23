"""Icon for each source: monitors → generic; windows → the real `.desktop` of the app id, with aliases for app ids
that match no .desktop (Chromium profiles, Xwayland classes…).

`candidates()` is pure and testable without GTK; `resolve()` queries Gio and is cached per app id.
"""

from functools import lru_cache

from . import logs

log = logs.get("icons")

MONITOR_ICON = "video-display"
GENERIC_ICON = "application-x-executable"

# app id → .desktop id (without extension) or theme icon name. Last resort after looking up the real .desktop.
ALIASES = {
    "kitty": "kitty",
    "herdr": "utilities-terminal",
    "org.kde.dolphin": "system-file-manager",
}


def candidates(app_id: str) -> list[str]:
    """.desktop ids to try, in order, for an app id. No duplicates."""
    if not app_id:
        return []
    ids = [app_id]
    if app_id.startswith("chrome-"):  # Chromium PWAs and profiles: chrome-<origin>__-<profile>
        ids.append("chromium")
    if app_id.startswith("firefox"):
        ids.append("firefox")
    if "." in app_id:  # org.kde.dolphin → dolphin; org.chromium.Chromium → chromium
        last = app_id.rsplit(".", 1)[-1]
        ids += [last, last.lower()]
    ids.append(app_id.lower())
    if alias := ALIASES.get(app_id):
        ids.append(alias)
    seen: list[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen


def _gio_desktop():
    """PyGObject ≥ 3.56 moves DesktopAppInfo to GioUnix; older versions keep it in Gio."""
    try:
        from gi.repository import GioUnix

        return GioUnix
    except (ImportError, ValueError):
        from gi.repository import Gio

        return Gio


def _desktop(ident: str):
    """`DesktopAppInfo.new` raises TypeError (constructor returned NULL) when the .desktop does not exist."""
    try:
        return _gio_desktop().DesktopAppInfo.new(f"{ident}.desktop")
    except TypeError:
        return None


def _desktop_by_wm_class(app_id: str):
    """Search every installed app for a matching StartupWMClass (Xwayland/Electron case)."""
    from gi.repository import Gio

    target = app_id.lower()
    for app in Gio.AppInfo.get_all():
        wm_class = getattr(app, "get_startup_wm_class", lambda: None)()
        if wm_class and wm_class.lower() == target:
            return app
    return None


def _app_info(app_id: str):
    """The DesktopAppInfo for an app id, or None. Same search order as the icon."""
    for ident in candidates(app_id):
        app = _desktop(ident)
        if app is not None:
            return app
    return _desktop_by_wm_class(app_id) if app_id else None


@lru_cache(maxsize=256)
def app_name(app_id: str) -> str:
    """Human name from the .desktop (`Name=`), else the app id itself. Never raises."""
    if not app_id:
        return ""
    try:
        app = _app_info(app_id)
        if app is not None and app.get_display_name():
            return app.get_display_name()
    except Exception as e:  # noqa: BLE001
        log.debug("name for %r: %s", app_id, e)
    return app_id


@lru_cache(maxsize=256)
def resolve(app_id: str, is_monitor: bool = False):
    """Return a `Gio.Icon` ready for `Gtk.Image.new_from_gicon`. Never raises."""
    from gi.repository import Gio

    if is_monitor:
        return Gio.ThemedIcon.new(MONITOR_ICON)
    try:
        for ident in candidates(app_id):
            app = _desktop(ident)
            if app is not None and app.get_icon() is not None:
                return app.get_icon()
        app = _desktop_by_wm_class(app_id) if app_id else None
        if app is not None and app.get_icon() is not None:
            return app.get_icon()
        if alias := ALIASES.get(app_id):
            return Gio.ThemedIcon.new(alias)
    except Exception as e:  # noqa: BLE001  — an icon must never take the picker down
        log.debug("icon for %r: %s", app_id, e)
    return Gio.ThemedIcon.new(GENERIC_ICON)
