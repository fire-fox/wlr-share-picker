"""Fallback without GTK: any dmenu-compatible menu reading `--dmenu` from stdin. The first one installed wins."""

import shutil
import subprocess

from . import logs
from .config import Config
from .i18n import _

log = logs.get("dmenu")

PROMPT = _("Share: ")
CANDIDATES: list[list[str]] = [
    ["fuzzel", "--dmenu", "--prompt", PROMPT, "--lines", "12", "--width", "70"],
    ["wofi", "--dmenu", "--prompt", PROMPT.strip(": ")],
    ["bemenu", "--prompt", PROMPT.strip(": ")],
    ["rofi", "-dmenu", "-p", PROMPT.strip(": ")],
]


def command(cfg: Config) -> list[str] | None:
    if cfg.dmenu:
        return cfg.dmenu if shutil.which(cfg.dmenu[0]) else None
    return next((c for c in CANDIDATES if shutil.which(c[0])), None)


def pick(lines: list[str], cfg: Config) -> str | None:
    """Return the chosen line (as is, newline included) or None when cancelled or no dmenu is available."""
    cmd = command(cfg)
    if cmd is None:
        log.error("no dmenu installed (%s): cancelling", ", ".join(c[0] for c in CANDIDATES))
        return None
    log.info("using fallback %s", cmd[0])
    try:
        # S603: the command is the user's own config or a fixed candidate; the portal's lines go on stdin, never argv.
        r = subprocess.run(cmd, input="".join(lines), capture_output=True, text=True, timeout=300)  # noqa: S603
    except (OSError, subprocess.SubprocessError) as e:
        log.error("%s failed: %s", cmd[0], e)
        return None
    chosen = r.stdout
    if not chosen.strip():
        return None
    # Only return lines the portal sent: a dmenu with free text could make one up.
    valid = {ln.rstrip("\r\n") for ln in lines}
    text = chosen.rstrip("\r\n")
    if text not in valid:
        log.warning("%s returned a line that was not in the list: %r", cmd[0], text)
        return None
    return text + "\n"
