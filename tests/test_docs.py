"""The README and config.example.toml document every input: config keys and command-line options."""

import argparse
import re
from dataclasses import fields
from pathlib import Path

from compartir_selector import cli
from compartir_selector.config import Config

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
EXAMPLE = (ROOT / "config.example.toml").read_text(encoding="utf-8")


def test_readme_lists_every_config_key():
    missing = [f.name for f in fields(Config) if f"| `{f.name}` |" not in README]
    assert not missing


def test_example_config_lists_every_key():
    present = set(re.findall(r"^# \[?(\w+)\]?\s*(?:=|\s#)", EXAMPLE, re.M))
    assert {f.name for f in fields(Config)} <= present


def test_readme_lists_every_visible_option():
    options = [
        opt
        for action in cli.parser()._actions
        if action.help is not argparse.SUPPRESS
        for opt in action.option_strings
        if opt.startswith("--")
    ]
    assert options and all(f"`{opt}" in README for opt in options)
