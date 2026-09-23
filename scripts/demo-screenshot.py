#!/usr/bin/env python3
"""Regenerate docs/screenshot.png from invented sources and drawn thumbnails: never a real screen.

The real `--screenshot` flag captures whatever windows are open, so it must never feed the README. This script
draws every thumbnail with cairo, serves them through a fake grim, uses a fixed English UI and the dark preset,
and reads nothing from the desktop (no config, no compositor, no portal sessions).
Usage: scripts/demo-screenshot.py [output.png]   (needs a Wayland session to render the window for ~3 s)
"""

import math
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["LANGUAGE"] = "en"  # before any compartir_selector import: gettext reads it once
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compartir_selector import cli  # noqa: E402

cli.relaunch_with_layer_shell()

import cairo  # noqa: E402

from compartir_selector import protocol, ui_gtk  # noqa: E402
from compartir_selector.captures import Capturer  # noqa: E402
from compartir_selector.compositor import Client  # noqa: E402
from compartir_selector.config import Config  # noqa: E402

# (portal line, app id, drawing, width, height)
SOURCES = [
    ("Monitor: DP-1 Acme Displays UW34 0001", "", "desktop_wide", 1720, 720),
    ("Monitor: HDMI-A-1 Acme Displays FHD24 0002", "", "desktop", 1280, 720),
    ("Window: Quarterly roadmap - Chromium (a1f3)", "chromium", "document", 1400, 900),
    ("Window: ~/src/compartir-selector - nvim (b2c4)", "kitty", "terminal", 1400, 900),
    ("Window: Design review.odp - LibreOffice Impress (c3d5)", "libreoffice-impress", "slides", 1400, 900),
    ("Window: big_buck_bunny.mkv - mpv (d4e6)", "mpv", "video", 1400, 788),
    ("Window: Daily notes - Obsidian (e5f7)", "obsidian", "notes", 700, 1100),
    ("Window: Downloads - Dolphin (f6a8)", "org.kde.dolphin", "files", 1400, 900),
]


def rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))


def box(ctx, x, y, w, h, color, r=0.0):
    ctx.set_source_rgb(*rgb(color))
    if r:
        ctx.new_sub_path()
        ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        ctx.close_path()
    else:
        ctx.rectangle(x, y, w, h)
    ctx.fill()


def text(ctx, x, y, s, size, color, bold=False):
    ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.set_source_rgb(*rgb(color))
    ctx.move_to(x, y)
    ctx.show_text(s)


def bars(ctx, x, y, width, rows, color, rng, gap=26, height=10, colors=None):
    """Paragraph-like rows of rounded bars (text stand-ins)."""
    for i in range(rows):
        cx = x
        remaining = width * rng.uniform(0.55, 1.0)
        while remaining > 30:
            w = min(remaining, rng.uniform(40, 170))
            box(ctx, cx, y + i * gap, w, height, rng.choice(colors) if colors else color, r=height / 2)
            cx += w + 10
            remaining -= w + 10


def chrome(ctx, w, h, bg, bar, dots=True):
    box(ctx, 0, 0, w, h, bg)
    box(ctx, 0, 0, w, 44, bar)
    if dots:
        for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            ctx.set_source_rgb(*rgb(c))
            ctx.arc(24 + i * 22, 22, 7, 0, 2 * math.pi)
            ctx.fill()


def document(ctx, w, h, rng):
    chrome(ctx, w, h, "#f1f3f4", "#dee1e6")
    box(ctx, 110, 8, 260, 36, "#f1f3f4", r=8)
    text(ctx, 128, 32, "Quarterly roadmap", 15, "#3c4043")
    box(ctx, 16, 54, w - 32, 34, "#ffffff", r=17)
    box(ctx, 190, 110, w - 380, h - 110, "#ffffff")
    text(ctx, 250, 190, "Quarterly roadmap", 38, "#202124", bold=True)
    bars(ctx, 250, 230, w - 500, 4, "#c4c7c5", rng)
    for i, (hgt, c) in enumerate(((150, "#8ab4f8"), (210, "#81c995"), (120, "#fdd663"), (260, "#f28b82"), (190, "#c58af9"))):
        box(ctx, 290 + i * 150, 620 - hgt, 90, hgt, c, r=6)
    bars(ctx, 250, 670, w - 500, 6, "#c4c7c5", rng)


def terminal(ctx, w, h, rng):
    chrome(ctx, w, h, "#1e1e2e", "#181825", dots=False)
    text(ctx, 20, 29, "~/src/compartir-selector - nvim", 15, "#a6adc8")
    palette = ["#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#cba6f7", "#94e2d5", "#cdd6f4", "#cdd6f4"]
    for i in range(30):
        y = 70 + i * 27
        text(ctx, 18, y + 10, f"{i + 1:3d}", 15, "#585b70")
        indent = rng.choice((0, 0, 1, 1, 2, 3))
        bars(ctx, 80 + indent * 34, y, rng.uniform(250, 900), 1, "#cdd6f4", rng, height=11, colors=palette)
    box(ctx, 0, h - 34, w, 34, "#313244")
    box(ctx, 0, h - 34, 110, 34, "#a6e3a1")
    text(ctx, 20, h - 11, "NORMAL", 15, "#1e1e2e", bold=True)


def slides(ctx, w, h, rng):
    chrome(ctx, w, h, "#2b2b2b", "#3c3c3c", dots=False)
    box(ctx, 0, 44, w, 40, "#333333")
    for i in range(5):
        box(ctx, 20, 110 + i * 150, 200, 120, "#ffffff" if i else "#ffb866", r=4)
        box(ctx, 26, 116 + i * 150, 188, 108, "#f6f5f2")
    box(ctx, 250, 110, w - 290, h - 150, "#fdfcfa", r=2)
    text(ctx, 320, 230, "Design review", 56, "#1c1b1a", bold=True)
    bars(ctx, 320, 280, 520, 3, "#b9b6ae", rng)
    ctx.set_source_rgb(*rgb("#ffb866"))
    ctx.arc(w - 320, 470, 150, 0, 2 * math.pi)
    ctx.fill()
    box(ctx, w - 560, 520, 220, 220, "#6c8ebf", r=18)
    box(ctx, 320, 520, 420, 22, "#e2ded5", r=11)
    box(ctx, 320, 560, 320, 22, "#e2ded5", r=11)


def video(ctx, w, h, rng):
    sky = cairo.LinearGradient(0, 0, 0, h)
    sky.add_color_stop_rgb(0, *rgb("#2d3a8c"))
    sky.add_color_stop_rgb(0.6, *rgb("#f08a5d"))
    sky.add_color_stop_rgb(1, *rgb("#f9d56e"))
    ctx.set_source(sky)
    ctx.paint()
    ctx.set_source_rgb(*rgb("#fff3c4"))
    ctx.arc(w * 0.68, h * 0.55, 70, 0, 2 * math.pi)
    ctx.fill()
    for color, base, amp in (("#4a5d23", 0.72, 60), ("#2f3e16", 0.82, 45)):
        ctx.set_source_rgb(*rgb(color))
        ctx.move_to(0, h)
        ctx.line_to(0, h * base)
        for x in range(0, w + 60, 60):
            ctx.line_to(x, h * base - amp * math.sin(x / 190 + base * 7))
        ctx.line_to(w, h)
        ctx.close_path()
        ctx.fill()
    box(ctx, 0, h - 56, w, 56, "#000000")
    box(ctx, 70, h - 32, w - 140, 8, "#555555", r=4)
    box(ctx, 70, h - 32, (w - 140) * 0.37, 8, "#e0e0e0", r=4)
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(24, h - 42)
    ctx.line_to(24, h - 14)
    ctx.line_to(46, h - 28)
    ctx.close_path()
    ctx.fill()


def notes(ctx, w, h, rng):
    chrome(ctx, w, h, "#1e1e1e", "#262626", dots=False)
    text(ctx, 24, 29, "Daily notes", 15, "#bbbbbb")
    text(ctx, 40, 120, "Today", 40, "#e8e8e8", bold=True)
    for i in range(9):
        y = 170 + i * 58
        box(ctx, 40, y, 22, 22, "#7f6df2" if i % 3 == 0 else "#3a3a3a", r=5)
        bars(ctx, 80, y + 6, w - 140, 1, "#6b6b6b", rng, height=10)
    text(ctx, 40, 740, "Ideas", 30, "#e8e8e8", bold=True)
    bars(ctx, 40, 780, w - 90, 9, "#5a5a5a", rng, gap=30)


def files(ctx, w, h, rng):
    chrome(ctx, w, h, "#232629", "#2a2e32", dots=False)
    text(ctx, 20, 29, "Downloads", 15, "#c8c8c8")
    box(ctx, 0, 44, 260, h - 44, "#1b1e20")
    for i in range(8):
        box(ctx, 24, 76 + i * 44, 22, 18, "#3daee9" if i == 2 else "#5d6168", r=3)
        bars(ctx, 58, 80 + i * 44, 150, 1, "#7a7f86", rng, height=9)
    colors = ["#3daee9", "#f67400", "#27ae60", "#9b59b6", "#fdbc4b", "#da4453"]
    for row in range(4):
        for col in range(6):
            x, y = 310 + col * 180, 90 + row * 190
            box(ctx, x, y + 14, 120, 90, rng.choice(colors), r=10)
            box(ctx, x, y, 56, 26, "#4d5257", r=6)
            box(ctx, x + 10, y + 124, 100, 10, "#7a7f86", r=5)


# Windows laid out on each monitor's wallpaper: (drawing, x, y, width, height) as fractions of the screen.
DESKTOPS = {
    "desktop_wide": [
        ("terminal", 0.01, 0.06, 0.32, 0.92),
        ("document", 0.34, 0.06, 0.32, 0.92),
        ("slides", 0.67, 0.06, 0.32, 0.92),
    ],
    "desktop": [("files", 0.02, 0.08, 0.6, 0.86), ("video", 0.64, 0.3, 0.34, 0.42)],
}
DRAW = {"document": document, "terminal": terminal, "slides": slides, "video": video, "notes": notes, "files": files}


def desktop(ctx, w, h, rng, layout):
    wall = cairo.LinearGradient(0, 0, w, h)
    wall.add_color_stop_rgb(0, *rgb("#1f2544"))
    wall.add_color_stop_rgb(1, *rgb("#474f7a"))
    ctx.set_source(wall)
    ctx.paint()
    box(ctx, 0, 0, w, 26, "#11131f")
    for name, x, y, ww, hh in layout:
        sub = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1400, 900)
        DRAW[name](cairo.Context(sub), 1400, 900, random.Random(name))
        ctx.save()
        ctx.translate(x * w, y * h)
        ctx.scale(ww * w / 1400, hh * h / 900)
        ctx.set_source_surface(sub, 0, 0)
        ctx.paint()
        ctx.restore()


def render(kind: str, width: int, height: int, target: Path) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    rng = random.Random(kind)
    if kind in DESKTOPS:
        desktop(ctx, width, height, rng, DESKTOPS[kind])
    else:
        DRAW[kind](ctx, width, height, rng)
    surface.write_to_png(str(target))


class StillPicker(ui_gtk.Picker):
    """Ignores the real pointer, so wherever the mouse happens to be the first card stays marked."""

    def _on_pointer(self, *_args) -> None:
        pass


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "screenshot.png").resolve()
    work = Path(tempfile.mkdtemp(prefix="compartir-selector-demo-"))
    lines = [line + "\n" for line, *_ in SOURCES]
    sources = protocol.parse(lines)
    for (_line, _app, kind, w, h), source in zip(SOURCES, sources, strict=True):
        render(kind, w, h, work / f"{source.raw_id or source.id}.png")
    grim = work / "grim"  # copies the drawing for `-o NAME` / `-T ID` to the target (last argument)
    grim.write_text(
        '#!/bin/sh\nwhile [ $# -gt 1 ]; do case "$1" in -o|-T) id="$2"; shift;; esac; shift; done\n'
        f'exec cp "{work}/$id.png" "$1"\n'
    )
    grim.chmod(0o755)
    clients = {s.id: Client(app_id=app, title=s.name) for (_l, app, *_), s in zip(SOURCES, sources, strict=True) if app}
    cfg = Config(theme="dark", columns=4, refresh_seconds=0)
    capturer = Capturer(cfg, grim=[str(grim)])
    try:
        StillPicker(sources, cfg, capturer, clients, 0, out, ["chromium"]).run([])
    finally:
        capturer.cleanup()
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
