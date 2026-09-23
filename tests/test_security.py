"""Security invariants (see SECURITY.md): what the picker may run, render, keep and send."""

import ast
import stat
from pathlib import Path

from compartir_selector import protocol
from compartir_selector.captures import Capturer

PACKAGE = Path(__file__).resolve().parent.parent / "compartir_selector"
MODULES = {p.name: p.read_text(encoding="utf-8") for p in sorted(PACKAGE.glob("*.py"))}


def _imports(text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_shell_anywhere():
    """Window titles and ids reach grim and the dmenu: always as argv elements or stdin, never through a shell."""
    for name, text in MODULES.items():
        for construct in ("shell=True", "os.system(", "os.popen(", "subprocess.getoutput(", "subprocess.getstatusoutput("):
            assert construct not in text, f"{name}: {construct}"


def test_titles_are_never_rendered_as_markup():
    """Any app chooses its window title; GTK labels only parse Pango markup when asked to."""
    for name, text in MODULES.items():
        assert "markup" not in text, name


def test_nothing_talks_to_the_network():
    """The README promises that nothing leaves the machine."""
    network = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "requests", "httpx", "aiohttp"}
    for name, text in MODULES.items():
        assert not _imports(text) & network, name


def test_no_unsafe_deserialisation():
    for name, text in MODULES.items():
        assert not _imports(text) & {"pickle", "marshal", "shelve"}, name
        assert "eval(" not in text and "exec(" not in text, name


def test_thumbnails_live_in_a_private_directory_removed_on_cleanup(cfg, fake_grim):
    capturer = Capturer(cfg, grim=fake_grim)
    assert stat.S_IMODE(capturer.directory.stat().st_mode) == 0o700
    thumbnail = capturer.capture(0, protocol.parse(["Monitor: DP-1\n"])[0])
    assert thumbnail is not None and thumbnail.parent == capturer.directory
    capturer.cleanup()
    assert not capturer.directory.exists()
