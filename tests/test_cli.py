"""End to end through a subprocess, the way the portal launches it: the list on stdin, the choice on stdout."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "wlr-share-picker"
LINES = "Monitor: DP-1 ASUS\nWindow: Roamgate (1f8f)\n"


def _run(stdin: str, extra_env: dict, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("WLR_SHARE_PICKER_")}
    env["XDG_RUNTIME_DIR"] = tempfile.mkdtemp()  # fresh choice memory per call unless the test shares one
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args], input=stdin, capture_output=True, text=True, env=env, timeout=30
    )


def test_dmenu_returns_the_line_as_is(fake_dmenu, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'frontend = "dmenu"\ndmenu = ["{fake_dmenu}"]\n')
    r = _run(LINES, {"DMENU_PICK": "2"}, "--config", str(cfg))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "Window: Roamgate (1f8f)\n"


def test_cancel_prints_nothing(fake_dmenu, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'dmenu = ["{fake_dmenu}"]\n')
    r = _run(LINES, {"WLR_SHARE_PICKER_FRONTEND": "dmenu"}, "--config", str(cfg))
    assert r.returncode == 0 and r.stdout == ""


def test_empty_stdin_exits_cleanly():
    r = _run("", {"WLR_SHARE_PICKER_FRONTEND": "dmenu"})
    assert r.returncode == 0 and r.stdout == ""


def test_no_fallback_and_no_gtk_exits_with_1(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('frontend = "dmenu"\nfallback = false\n')
    r = _run(LINES, {}, "--config", str(cfg))
    assert r.returncode == 1 and r.stdout == ""
    assert "fallback disabled" in r.stderr


def test_version():
    r = _run("", {}, "--version")
    assert r.returncode == 0 and "wlr-share-picker 0." in r.stdout


def test_second_call_reuses_the_choice_without_asking(fake_dmenu, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'frontend = "dmenu"\ndmenu = ["{fake_dmenu}"]\nreuse_choice_seconds = 30\n')
    runtime = {"XDG_RUNTIME_DIR": str(tmp_path)}
    first = _run(LINES, {**runtime, "DMENU_PICK": "2"}, "--config", str(cfg))
    assert first.stdout == "Window: Roamgate (1f8f)\n"
    # second call: the fake dmenu would cancel (no DMENU_PICK), but the memory answers first
    second = _run("Monitor: DP-1 ASUS\nWindow: Roamgate - other title (1f8f)\n", runtime, "--config", str(cfg))
    assert second.returncode == 0 and second.stdout == "Window: Roamgate - other title (1f8f)\n"
    assert "reusing the choice" in second.stderr


def test_fallback_applies_the_hide_rules(tmp_path):
    """The dmenu gets the filtered list: a hidden title never shows up there either."""
    shown = tmp_path / "shown.txt"
    menu = tmp_path / "menu"
    menu.write_text(f'#!/bin/sh\ncat > "{shown}"\nexit 1\n')
    menu.chmod(0o755)
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'frontend = "dmenu"\ndmenu = ["{menu}"]\nhide_titles = ["secret"]\n')
    r = _run(LINES + "Window: secret notes (2a2a)\n", {}, "--config", str(cfg))
    assert r.returncode == 0 and r.stdout == ""
    assert shown.read_text() == LINES


def test_relaunched_process_gives_children_the_original_preload(monkeypatch):
    from wlr_share_picker import cli

    monkeypatch.setenv(cli.RELAUNCHED, "1")
    monkeypatch.setenv("LD_PRELOAD", "libgtk4-layer-shell.so.0:libmine.so")
    monkeypatch.setenv(cli.PRELOAD_BEFORE, "libmine.so")
    cli.relaunch_with_layer_shell()
    assert os.environ["LD_PRELOAD"] == "libmine.so" and cli.PRELOAD_BEFORE not in os.environ
    monkeypatch.setenv("LD_PRELOAD", "libgtk4-layer-shell.so.0")
    monkeypatch.setenv(cli.PRELOAD_BEFORE, "")
    cli.relaunch_with_layer_shell()
    assert "LD_PRELOAD" not in os.environ


def test_no_dmenu_installed_exits_with_1(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('frontend = "dmenu"\ndmenu = ["/no/such/menu"]\n')
    r = _run(LINES, {}, "--config", str(cfg))
    assert r.returncode == 1 and r.stdout == ""
    assert "no dmenu available" in r.stderr and "cancelled by the user" not in r.stderr
