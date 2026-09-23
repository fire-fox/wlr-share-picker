"""Entry point: the portal's stdin → picker → stdout. Exit codes: 0 whenever an answer was possible (choosing
or cancelling both count), 1 when nothing could be shown, 2 on wrong usage."""

import argparse
import ctypes.util
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__, compositor, config, logs, protocol, recent, requester

log = logs.get("cli")

RELAUNCHED = "COMPARTIR_SELECTOR_RELAUNCHED"
PRELOAD_BEFORE = "COMPARTIR_SELECTOR_PRELOAD_BEFORE"  # the LD_PRELOAD the process had before relaunching
LAYER_SHELL_DIRS = ("/usr/lib", "/usr/lib64", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu")


def layer_shell_library() -> str | None:
    """Path or soname of libgtk4-layer-shell, if installed."""
    if so := ctypes.util.find_library("gtk4-layer-shell"):
        return so
    for base in LAYER_SHELL_DIRS:
        p = Path(base) / "libgtk4-layer-shell.so"
        if p.exists():
            return str(p)
    return None


def relaunch_with_layer_shell() -> None:
    """gtk4-layer-shell must be loaded before libwayland; from Python that only works with LD_PRELOAD, so the
    process replaces itself once. Without it GTK opens a normal (tiled) window instead of an overlay layer.
    Once relaunched the library is already loaded, so LD_PRELOAD goes back to what it was: otherwise every grim
    and IPC call would load GTK too (mmsg 4 → 16 ms) with the layer-shell shim hooked into its libwayland."""
    if os.environ.get(RELAUNCHED) == "1":
        _restore_preload()
        return
    so = layer_shell_library()
    if so is None or so in os.environ.get("LD_PRELOAD", ""):
        return
    env = dict(os.environ)
    env[RELAUNCHED] = "1"
    env[PRELOAD_BEFORE] = env.get("LD_PRELOAD", "")
    env["LD_PRELOAD"] = f"{so}:{env['LD_PRELOAD']}" if env.get("LD_PRELOAD") else so
    argv0 = sys.argv[0]
    if os.path.isfile(argv0):
        cmd = [sys.executable, argv0, *sys.argv[1:]]
    else:
        cmd = [sys.executable, "-m", "compartir_selector", *sys.argv[1:]]
    try:
        # S606: re-executes this same interpreter and script with our own argv, only adding LD_PRELOAD.
        os.execve(sys.executable, cmd, env)  # noqa: S606
    except OSError as e:
        log.warning("could not relaunch with LD_PRELOAD (%s): the window may not open as a layer", e)


def _restore_preload() -> None:
    before = os.environ.pop(PRELOAD_BEFORE, None)
    if before is None:
        return
    if before:
        os.environ["LD_PRELOAD"] = before
    else:
        os.environ.pop("LD_PRELOAD", None)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compartir-selector", description="Thumbnail picker for xdg-desktop-portal-wlr (chooser_type=dmenu)."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--frontend", choices=["auto", "gtk", "dmenu"], help="force a frontend (default: config or auto)")
    p.add_argument("--config", type=Path, help="path to config.toml")
    p.add_argument("--debug", action="store_true", help="verbose stderr (same as COMPARTIR_SELECTOR_DEBUG=1)")
    p.add_argument("--screenshot", type=Path, metavar="PNG", help=argparse.SUPPRESS)  # dev aid: save the window and quit
    return p


def _args(argv: list[str] | None) -> argparse.Namespace:
    return parser().parse_args(argv)


def _fallback(lines: list[str], cfg: config.Config) -> tuple[str | None, bool]:
    """(choice, could_show), like `_gtk`: no fallback allowed or no dmenu installed means nothing was shown."""
    from . import ui_dmenu

    if not cfg.fallback:
        log.error("GTK unavailable and fallback disabled in config: cancelling")
        return None, False
    if ui_dmenu.command(cfg) is None:
        log.error("no dmenu available (%s): cancelling", " ".join(cfg.dmenu) or ", ".join(c[0] for c in ui_dmenu.CANDIDATES))
        return None, False
    return ui_dmenu.pick(lines, cfg), True


def _titles(backend: compositor.Compositor) -> dict[str, str]:
    """toplevel id → current title, straight from the compositor (the portal's list is a snapshot)."""
    return {ident: c.title for ident, c in compositor.safe_clients(backend).items() if c.title}


def _gtk(
    sources, cfg: config.Config, clients: dict, requesters: list, screenshot: Path | None, titles
) -> tuple[str | None, bool]:
    """(choice, could_show). If GTK never gets to show anything, the caller decides about the fallback."""
    from .captures import Capturer

    try:
        from . import ui_gtk
    except (ImportError, ValueError) as e:  # ValueError: gi.require_version without the typelib
        log.warning("GTK 4 or gtk4-layer-shell unavailable (%s)", e)
        return None, False
    capturer = Capturer(cfg)
    if not capturer.available():
        log.warning("grim is not installed: cards without thumbnails")
    app_ids = {ident: c.app_id for ident, c in clients.items()}
    preselect = recent.preferred(sources, app_ids) if cfg.remember_choice else None
    try:
        names = [r.app_id for r in requesters] if cfg.show_requester else []
        return ui_gtk.pick(sources, cfg, capturer, clients, preselect, screenshot, names, titles), True
    except Exception:  # noqa: BLE001 — any GTK failure falls back, never leaves the portal without an answer
        log.exception("the GTK picker failed")
        return None, False
    finally:
        capturer.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if args.debug:
        os.environ["COMPARTIR_SELECTOR_DEBUG"] = "1"
    cfg = config.load(args.config)
    if args.frontend:
        cfg = replace(cfg, frontend=args.frontend)
    logs.configure(cfg.debug)
    if cfg.frontend != "dmenu":
        relaunch_with_layer_shell()

    if sys.stdin.isatty():
        log.error("expected the source list on stdin (xdg-desktop-portal-wlr sends it); see --help")
        return 2
    lines = sys.stdin.readlines()
    sources = protocol.parse(lines)
    log.info(
        "asked for %d monitor(s) and %d window(s)",
        sum(s.is_monitor for s in sources),
        sum(not s.is_monitor for s in sources),
    )
    if not lines:
        return 0
    backend = compositor.detect()
    clients = compositor.safe_clients(backend) if sources else {}
    app_ids = {ident: c.app_id for ident, c in clients.items()}
    requesters = requester.detect() if sources else []
    pid = requesters[0].pid if len(requesters) == 1 else 0
    if reused := recent.recall(sources, cfg, requester_pid=pid):
        sys.stdout.write(reused.line)
        sys.stdout.flush()
        return 0
    sources = protocol.exclude(sources, app_ids, cfg.hide_app_ids, cfg.hide_titles)
    if automatic := requester.auto_choice(requesters, sources, app_ids, cfg.auto):
        log.info("[auto] answering %s with %s %r", ", ".join(r.app_id for r in requesters), automatic.kind, automatic.name)
        sys.stdout.write(automatic.line)
        sys.stdout.flush()
        recent.remember(automatic.line, persistent=False, requester_pid=pid)
        return 0

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # for the non-GTK path; atexit removes temp files

    choice: str | None = None
    shown = False
    if cfg.frontend in ("auto", "gtk") and sources:
        choice, shown = _gtk(sources, cfg, clients, requesters, args.screenshot, lambda: _titles(backend))
    if not shown and cfg.frontend != "gtk":
        # The filtered list (hide_app_ids/hide_titles apply here too); the raw lines only if none could be parsed.
        choice, shown = _fallback([s.line for s in sources] or lines, cfg)

    if choice:
        choice = protocol.refresh_title(choice, _titles(backend))
        sys.stdout.write(choice)
        sys.stdout.flush()
        log.info("answered: %s", choice.strip())
        chosen = protocol.parse_line(choice)
        recent.remember(choice, app_ids.get(chosen.id, "") if chosen else "", persistent=cfg.remember_choice, requester_pid=pid)
    else:
        log.info("cancelled by the user" if shown else "nothing could be shown")
    return 0 if shown else 1
