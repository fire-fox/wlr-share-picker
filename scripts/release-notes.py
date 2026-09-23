#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md (the release notes). Exit 1 when it is missing or empty.
Usage: scripts/release-notes.py 0.5.0"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(text: str, version: str) -> str | None:
    """Body under `## <version>` (anything may follow the version on the heading), up to the next `## `."""
    heading = re.compile(rf"## {re.escape(version)}(\s|$)")
    body: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(heading.match(line))
            continue
        if inside:
            body.append(line)
    return "\n".join(body).strip() or None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    notes = section(CHANGELOG.read_text(encoding="utf-8"), argv[1])
    if notes is None:
        print(f"CHANGELOG.md has no notes for {argv[1]}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
