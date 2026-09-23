"""UI parts testable without a display: column computation and the fixed-box paintable."""

import pytest

from compartir_selector.config import Config

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
except ValueError as e:  # typelib not installed: skip, as the picker itself falls back to dmenu
    pytest.skip(f"GTK 4 or gtk4-layer-shell typelib missing: {e}", allow_module_level=True)
ui_gtk = pytest.importorskip("compartir_selector.ui_gtk")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


def test_columns_from_monitor_width():
    cfg = Config(thumbnail_width=320, max_columns=6)
    assert ui_gtk.columns_for(3440, 20, cfg) == 6  # ultrawide: config cap
    assert ui_gtk.columns_for(1920, 20, cfg) == 4
    assert ui_gtk.columns_for(1366, 20, cfg) == 3
    assert ui_gtk.columns_for(1920, 2, cfg) == 2  # never more columns than sources
    assert ui_gtk.columns_for(400, 5, cfg) == 1
    assert ui_gtk.columns_for(3440, 20, Config(columns=3)) == 3


def _texture(width: int, height: int) -> Gdk.Texture:
    data = GLib.Bytes.new(bytes(width * height * 4))
    return Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8A8, data, width * 4)


@pytest.mark.parametrize("width,height", [(1204, 503), (200, 900), (10, 10)])
def test_thumbnail_always_measures_the_box(width, height):
    t = ui_gtk.Thumbnail(_texture(width, height), 320, 200)
    assert (t.get_intrinsic_width(), t.get_intrinsic_height()) == (320, 200)
    snap = Gtk.Snapshot.new()
    t.snapshot(snap, 320, 200)  # must not raise
    assert snap.to_node() is not None


def test_thumbnail_without_upscale_keeps_natural_size():
    t = ui_gtk.Thumbnail(_texture(48, 48), 320, 200, upscale=False)
    assert (t.get_intrinsic_width(), t.get_intrinsic_height()) == (320, 200)
    snap = Gtk.Snapshot.new()
    t.snapshot(snap, 320, 200)
    node = snap.to_node()
    assert node is not None
    # the drawn content is 48×48 centred, not the whole box
    bounds = node.get_bounds()
    assert (round(bounds.size.width), round(bounds.size.height)) == (48, 48)
    assert (round(bounds.origin.x), round(bounds.origin.y)) == (136, 76)


def test_filter_matches_what_the_card_shows():
    """Typing the (translated) words on a monitor card finds it: «Pantalla» in Spanish, «Screen» in English."""
    from compartir_selector import protocol
    from compartir_selector.compositor import Client

    monitor, window = protocol.parse(["Monitor: DP-1 ASUS\n", "Window: Roamgate (0b)\n"])
    card = ui_gtk.Card(0, monitor, Client(app_id=""))
    assert "DP-1" in card.name and card.matches(card.name.split()[0]) and card.matches("asus")
    other = ui_gtk.Card(1, window, Client(app_id="nothing-installed-like-this"))
    assert other.matches("roamgate") and not other.matches(card.name.split()[0])
    other.title = "Live title"
    assert other.name == "Live title" and other.matches("live")
