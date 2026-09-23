"""Security invariants (see SECURITY.md): what the picker may run, render, keep and send."""

import ast
import stat
import subprocess
import unicodedata
from pathlib import Path

from compartir_selector import protocol
from compartir_selector.captures import Capturer

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "compartir_selector"
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


SKIPPED_DIRS = {".git", "__pycache__", ".hypothesis", ".pytest_cache", ".ruff_cache", "mutants", "build", "dist"}


def _repository_files() -> list[Path]:
    """Every file of the repository: tracked plus new ones not ignored (git), or every file when there is no git
    (a release tarball, mutmut's copy)."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode()
        paths = [ROOT / name for name in listed.split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in ROOT.rglob("*") if not SKIPPED_DIRS & set(p.relative_to(ROOT).parts)]
    return sorted(p for p in paths if p.is_file() and not any(part.endswith(".egg-info") for part in p.relative_to(ROOT).parts))


def _text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def test_no_invisible_or_direction_changing_characters():
    """Characters that change what a reviewer sees without being seen themselves: bidirectional controls
    ("Trojan Source", CVE-2021-42574), zero-width characters, soft hyphens, byte order marks (Unicode category Cf).
    The code a reviewer reads must be the code that runs."""
    found = []
    for path in _repository_files():
        text = _text(path)
        for number, line in enumerate((text or "").splitlines(), 1):
            for char in line:
                if unicodedata.category(char) == "Cf":
                    name = unicodedata.name(char, "unnamed")
                    found.append(f"{path.relative_to(ROOT)}:{number}: U+{ord(char):04X} {name}")
    assert not found, "\n".join(found)


def test_only_known_binary_files():
    """A binary file cannot be reviewed; the xz backdoor (2024) hid in binary test files. Only these may exist."""
    allowed = {ROOT / "docs" / "screenshot.png", *PACKAGE.glob("locale/*/LC_MESSAGES/*.mo")}
    unexpected = [str(p.relative_to(ROOT)) for p in _repository_files() if _text(p) is None and p not in allowed]
    assert not unexpected, unexpected
