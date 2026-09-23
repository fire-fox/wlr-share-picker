"""Where the picker keeps its small files, and how they are written.

The short-lived memory can answer a portal request without showing the dialog, so nothing is read from or written
to a place another user could have prepared. The directories are `$XDG_RUNTIME_DIR/compartir-selector` (short-lived)
and `$XDG_STATE_HOME/compartir-selector` (persistent), created 0700 and accepted only when they are real
directories owned by this user. There is no fallback to /tmp: without `XDG_RUNTIME_DIR` the short-lived memory is
simply off. Files are written atomically with mode 0600.
"""

import json
import os
import stat
from pathlib import Path

from . import logs

log = logs.get("paths")

APP = "compartir-selector"


def _private_dir(base: Path) -> Path | None:
    """`base/compartir-selector`, created if needed; None when it is not a directory of ours (a symlink, a file,
    another owner) or cannot be created. An own directory with loose permissions is tightened to 0700."""
    path = base / APP
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        st = path.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
            log.warning("%s is not a directory owned by this user: not using it", path)
            return None
        if st.st_mode & 0o077:
            path.chmod(0o700)
    except OSError as e:
        log.debug("no private directory under %s: %s", base, e)
        return None
    return path


def runtime_dir() -> Path | None:
    """Short-lived files (gone at logout). None without `XDG_RUNTIME_DIR`: never /tmp, which others can write."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        log.debug("XDG_RUNTIME_DIR is not set: short-lived memory off")
        return None
    return _private_dir(Path(base))


def state_dir() -> Path | None:
    """Persistent files."""
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return _private_dir(Path(base))


def write_json(path: Path, data) -> None:
    """Atomic write, 0600 from the start (no window with looser permissions). Raises OSError."""
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    tmp.replace(path)


def read_json(path: Path):
    """The parsed file, or None when it is missing, unreadable or not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
