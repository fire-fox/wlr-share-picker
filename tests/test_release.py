"""Release metadata that must agree before tagging (the release workflow checks the same against the tag)."""

import importlib.util
import re
from pathlib import Path

import wlr_share_picker

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release-notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)


def test_pkgbuild_and_package_share_the_version():
    pkgver = re.search(r"^pkgver=(.+)$", (ROOT / "packaging" / "PKGBUILD").read_text(), re.M).group(1)
    assert pkgver == wlr_share_picker.__version__


def test_the_current_version_has_release_notes():
    assert release_notes.section((ROOT / "CHANGELOG.md").read_text(), wlr_share_picker.__version__)


def test_section_parsing():
    text = (
        "# Changelog\n\n## Unreleased\n- next\n\n## 1.2.0 — 2026-01-02\n- b\n- c\n\n## 1.10.0\n- d\n\n## 1.1.0\n\n## 1.0.0\n- a\n"
    )
    assert release_notes.section(text, "Unreleased") == "- next"
    assert release_notes.section(text, "1.2.0") == "- b\n- c"
    assert release_notes.section(text, "1.1.0") is None  # heading without notes
    assert release_notes.section(text, "1.0.0") == "- a"
    assert release_notes.section(text, "1.1") is None  # never a prefix of another version
    assert release_notes.section(text, "2.0.0") is None
