import os
import stat
from pathlib import Path

import pytest

from compartir_selector.config import Config


@pytest.fixture
def cfg() -> Config:
    return Config(capture_timeout=1.0, capture_threads=2)


@pytest.fixture
def fake_grim(tmp_path: Path) -> list[str]:
    """A pretend `grim`: writes the target file, unless the id is `c0e1a` (sleeps) or `fa11a` (exits 1)."""
    script = tmp_path / "grim"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do case "$a" in c0e1a) exec sleep 10;; fa11a) exit 1;; esac; done\n'
        'eval "dest=\\${$#}"\n'
        'printf "jpg" > "$dest"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [str(script)]


@pytest.fixture
def fake_dmenu(tmp_path: Path) -> Path:
    """A dmenu that picks the line given in DMENU_PICK (1-based index) or cancels when it is empty."""
    script = tmp_path / "dmenu"
    script.write_text('#!/bin/sh\n[ -z "$DMENU_PICK" ] && exit 1\nsed -n "${DMENU_PICK}p"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def clean_env(monkeypatch):
    for v in (
        "MANGO_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "COMPARTIR_SELECTOR_CONFIG",
        "COMPARTIR_SELECTOR_DEBUG",
        "COMPARTIR_SELECTOR_FRONTEND",
        "COMPARTIR_SELECTOR_RELAUNCHED",
    ):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(os.devnull))
