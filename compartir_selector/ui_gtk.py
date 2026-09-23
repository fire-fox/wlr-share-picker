"""GTK 4 grid on an overlay layer (gtk4-layer-shell): thumbnail, icon and title per source.

Presentation only: receives the parsed sources, a capturer for the thumbnails and the compositor's clients.
Returns the chosen line or None. Importing this module already requires GTK: the caller catches that.
"""

import signal
import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Graphene, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

from . import icons, logs, search, theme  # noqa: E402
from .compositor import Client  # noqa: E402
from .config import Config  # noqa: E402
from .i18n import _  # noqa: E402
from .protocol import Source  # noqa: E402

log = logs.get("gtk")


class Thumbnail(GObject.Object, Gdk.Paintable):
    """Paintable with the fixed size of the card box, drawing its content centred and scaled inside.
    With the raw texture, Gtk.Picture requests a height proportional to the cell width, so a portrait
    window stretches the whole row; with this wrapper every card has the same size."""

    def __init__(self, content: Gdk.Paintable, width: int, height: int, upscale: bool = True):
        super().__init__()
        self.content = content  # grim texture, or a theme icon for "no image"
        self.width = width
        self.height = height
        self.upscale = upscale  # False: never scale above the natural size (icons)

    def do_get_intrinsic_width(self) -> int:
        return self.width

    def do_get_intrinsic_height(self) -> int:
        return self.height

    def do_get_intrinsic_aspect_ratio(self) -> float:
        return self.width / self.height

    def do_get_flags(self):
        return Gdk.PaintableFlags.SIZE | Gdk.PaintableFlags.CONTENTS

    def do_snapshot(self, snapshot, width: float, height: float) -> None:
        cw, ch = self.content.get_intrinsic_width() or 1, self.content.get_intrinsic_height() or 1
        f = min(width / cw, height / ch) if self.upscale else min(width / cw, height / ch, 1.0)
        w, h = cw * f, ch * f
        snapshot.save()
        snapshot.translate(Graphene.Point().init((width - w) / 2, (height - h) / 2))
        self.content.snapshot(snapshot, w, h)
        snapshot.restore()


CARD_MARGIN = 40  # padding + border + column spacing, per card
WINDOW_MARGIN = 44


def columns_for(monitor_width: int, n_sources: int, cfg: Config) -> int:
    """How many cards fit per row on the monitor (or the configured count), never more than there are sources."""
    c = cfg.columns if cfg.columns > 0 else int(monitor_width * 0.9 - WINDOW_MARGIN) // (cfg.thumbnail_width + CARD_MARGIN)
    return max(1, min(c, cfg.max_columns, max(1, n_sources)))


class Card:
    """One grid entry: widgets plus the searchable text and whether it currently passes the filter."""

    def __init__(self, index: int, source: Source, client: Client):
        self.index = index
        self.source = source
        self.client = client
        self.app_name = icons.app_name(client.app_id)
        self.title = source.name  # the window's current title, kept live while the picker is open
        self.box: Gtk.Box | None = None
        self.picture: Gtk.Picture | None = None
        self.name_label: Gtk.Label | None = None
        self.visible = True

    @property
    def name(self) -> str:
        """First line of the card, as shown (translated for monitors)."""
        return _("Screen {name}").format(name=self.source.name) if self.source.is_monitor else self.title

    @property
    def detail(self) -> str:
        """Second line of the card, as shown."""
        if self.source.is_monitor:
            return self.source.description or _("Full monitor")
        return self.app_name or _("Window")

    def matches(self, query: str) -> bool:
        """Against what the card shows plus the app id and the kind, so typing what you read always works."""
        s = self.source
        return search.matches(query, self.name, self.detail, self.client.app_id, s.kind)


class Picker(Gtk.Application):
    def __init__(
        self,
        sources: list[Source],
        cfg: Config,
        capturer,
        clients: dict[str, Client],
        preselect: int | None = None,
        screenshot: Path | None = None,
        requesters: list[str] | None = None,
        titles: Callable[[], dict[str, str]] | None = None,
    ):
        # NON_UNIQUE: if the portal launches two pickers (Chromium asks twice), each one is independent.
        super().__init__(application_id="dev.erik.compartir_selector", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.sources = sources
        self.cfg = cfg
        self.capturer = capturer
        self.clients = clients
        self.preselect = preselect if preselect is not None and 0 <= preselect < len(sources) else 0
        self.screenshot = screenshot  # development aid: save a PNG of the window once thumbnails are in, then quit
        self.requesters = requesters or []  # app ids of the apps asking, when known
        self.titles = titles  # toplevel id → current title, asked to the compositor on every refresh
        self._titles_pending = False
        self._pointer: tuple[float, float] | None = None
        self.active = 0
        self.columns = 1
        self.cards: list[Card] = []
        self.chosen: str | None = None
        self.window: Gtk.ApplicationWindow | None = None

    # --- construction ---------------------------------------------------------------------------------------

    def do_activate(self):
        display = Gdk.Display.get_default()
        palette = theme.build(self.cfg.theme, self.cfg.colors, Path(GLib.get_user_config_dir()))
        css = Gtk.CssProvider()
        css.load_from_data(theme.css(palette))
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        mon_width, mon_height = self._monitor_geometry(display)
        self.columns = columns_for(mon_width, len(self.sources), self.cfg)

        w = Gtk.ApplicationWindow(application=self, title=_("Share screen"))
        self.window = w
        Layer.init_for_window(w)
        Layer.set_layer(w, Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.EXCLUSIVE)
        Layer.set_namespace(w, "compartir-selector")
        w.set_default_size(self.columns * (self.cfg.thumbnail_width + CARD_MARGIN) + WINDOW_MARGIN, -1)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, margin_top=18, margin_bottom=14, margin_start=22, margin_end=22, spacing=6
        )
        w.set_child(box)
        box.append(self._title())
        hint = Gtk.Label(
            label=_("Arrows to move · Enter or click to share · 1-9 picks directly · type to filter · Esc to cancel"), xalign=0
        )
        hint.add_css_class("hint")
        box.append(hint)

        # The entry keeps the focus, so plain typing filters. Navigation keys are handled first by the
        # window's controller in the capture phase (see below): with set_key_capture_widget the entry would
        # swallow arrows, digits and Escape before the grid ever saw them.
        self.filter = Gtk.SearchEntry(placeholder_text=_("Filter by title or app"))
        self.filter.add_css_class("filter")
        self.filter.connect("search-changed", lambda *_: self._apply_filter())
        box.append(self.filter)

        self.grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=self.columns,
            min_children_per_line=self.columns,
            column_spacing=10,
            row_spacing=10,
            homogeneous=True,
            valign=Gtk.Align.START,
        )
        for i, source in enumerate(self.sources):
            client = Client(app_id="") if source.is_monitor else self.clients.get(source.id, Client(app_id=""))
            card = Card(i, source, client)
            self.cards.append(card)
            self.grid.append(self._build_card(card))
        self.grid.set_filter_func(lambda child: self.cards[child.get_index()].visible)
        self.nothing = Gtk.Label(label=_("Nothing matches"), visible=False)
        self.nothing.add_css_class("nothing")
        stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stack.append(self.grid)
        stack.append(self.nothing)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=True,
            max_content_height=int(mon_height * 0.8),
        )
        scroll.set_child(stack)  # wraps it in a Gtk.Viewport, used to keep the active card in view
        self.scroll = scroll
        box.append(scroll)

        footer = Gtk.Box(halign=Gtk.Align.END, margin_top=8)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.add_css_class("cancel")
        cancel.connect("clicked", lambda *_: self.finish(None))
        footer.append(cancel)
        box.append(footer)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        w.add_controller(keys)
        # Hover marks the card under the pointer only when the pointer really moves: a per-card "enter" would
        # also fire when keyboard scrolling slides cards under a still pointer and steal the selection.
        pointer = Gtk.EventControllerMotion()
        pointer.connect("motion", self._on_pointer)
        w.add_controller(pointer)
        w.connect("close-request", lambda *_: self.finish(None) or False)
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, s, self._on_signal, s)

        self._mark(self.preselect, reveal=True)
        w.present()
        self.filter.grab_focus()
        self.capturer.run_all(self.sources, self._thumbnail_ready)
        if self.cfg.refresh_seconds > 0:
            GLib.timeout_add(int(self.cfg.refresh_seconds * 1000), self._refresh)
        if self.screenshot is not None:
            GLib.timeout_add(3000, self._save_screenshot)

    def _title(self) -> Gtk.Widget:
        """«Chromium wants to share your screen» with its icon when the requester is known, else the plain question."""
        text = self.cfg.title
        if not text:
            names = [icons.app_name(a) or a for a in self.requesters]
            text = (
                _("{app} wants to share your screen").format(app=", ".join(names)) if names else _("What do you want to share?")
            )
        row = Gtk.Box(spacing=8)
        if self.requesters and not self.cfg.title:
            icon = Gtk.Image.new_from_gicon(icons.resolve(self.requesters[0]))
            icon.set_pixel_size(24)
            row.append(icon)
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title")
        row.append(label)
        return row

    def _thumbnail_height(self) -> int:
        return int(self.cfg.thumbnail_width * 5 / 8)

    @staticmethod
    def _monitor_geometry(display) -> tuple[int, int]:
        """Logical size of the narrowest monitor: the compositor decides where the layer opens, and a grid that
        fits the smallest one fits everywhere."""
        try:
            monitors = display.get_monitors()
            geometries = [monitors.get_item(i).get_geometry() for i in range(monitors.get_n_items())]
            if geometries:
                g = min(geometries, key=lambda g: g.width)
                return g.width, g.height
        except Exception as e:  # noqa: BLE001
            log.debug("no monitor geometry: %s", e)
        return 1920, 1080

    def _build_card(self, card: Card) -> Gtk.Box:
        source, client, i = card.source, card.client, card.index
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START)
        box.add_css_class("card")
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        picture.set_size_request(self.cfg.thumbnail_width, self._thumbnail_height())
        picture.add_css_class("empty")
        box.append(picture)

        row = Gtk.Box(spacing=8)
        icon = Gtk.Image.new_from_gicon(icons.resolve(client.app_id, source.is_monitor))
        icon.set_pixel_size(22)
        row.append(icon)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        name_label = Gtk.Label(label=card.name, xalign=0, ellipsize=3, max_width_chars=34)
        name_label.add_css_class("name")
        column.append(name_label)
        card.name_label = name_label
        detail_label = Gtk.Label(label=card.detail, xalign=0, ellipsize=3, max_width_chars=34)
        detail_label.add_css_class("detail")
        column.append(detail_label)
        row.append(column)
        if i < 9:
            shortcut = Gtk.Label(label=str(i + 1), valign=Gtk.Align.START)
            shortcut.add_css_class("shortcut")
            row.append(shortcut)
        box.append(row)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.finish(i))
        box.add_controller(click)
        card.box, card.picture = box, picture
        return box

    # --- thumbnails (arrive from capturer threads) ----------------------------------------------------------

    def _thumbnail_ready(self, i: int, path: Path | None) -> None:
        """Runs on the capture thread: the JPEG is decoded here (textures are immutable and thread-safe) so the
        main loop only swaps paintables, even with dozens of windows refreshing."""
        texture = None
        if path is not None:
            try:
                texture = Gdk.Texture.new_from_filename(str(path))
            except GLib.Error as e:
                log.info("unreadable thumbnail %s: %s", path, e)
                return
        GLib.idle_add(self._set_thumbnail, i, texture)

    def _set_thumbnail(self, i: int, texture: Gdk.Texture | None) -> bool:
        if self.chosen is not None or i >= len(self.cards):
            return False
        picture = self.cards[i].picture
        if texture is None:
            if picture.get_paintable() is not None and not picture.has_css_class("empty"):
                return False  # keep the last good frame when a refresh fails
            icon = Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).lookup_icon(
                "image-missing", None, 48, 1, Gtk.TextDirection.NONE, 0
            )
            picture.set_paintable(Thumbnail(icon, self.cfg.thumbnail_width, self._thumbnail_height(), upscale=False))
        else:
            picture.remove_css_class("empty")
            picture.set_paintable(Thumbnail(texture, self.cfg.thumbnail_width, self._thumbnail_height()))
        return False

    def _refresh(self) -> bool:
        """Periodic re-capture of the cards that pass the filter, so the thumbnails are live, plus the window
        titles. Skipped while the previous round is still running."""
        if self.chosen is not None:
            return GLib.SOURCE_REMOVE
        if not self.capturer.busy():
            self.capturer.run_all(self.sources, self._thumbnail_ready, skip_timed_out=True, only=set(self._visible_indexes()))
        if self.titles is not None and not self._titles_pending:
            self._titles_pending = True
            threading.Thread(target=self._fetch_titles, name="titles", daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _fetch_titles(self) -> None:
        """Compositor IPC off the main loop; the answer is applied there."""
        try:
            titles = self.titles() if self.titles else {}
        except Exception as e:  # noqa: BLE001 — stale titles are harmless
            log.debug("could not refresh titles: %s", e)
            titles = {}
        GLib.idle_add(self._apply_titles, titles)

    def _apply_titles(self, titles: dict[str, str]) -> bool:
        self._titles_pending = False
        if self.chosen is not None:
            return GLib.SOURCE_REMOVE
        changed = False
        for card in self.cards:
            current = titles.get(card.source.id) if not card.source.is_monitor else None
            if current and current != card.title:
                card.title = current
                card.name_label.set_label(card.name)
                changed = True
        if changed and self.filter.get_text():
            self._apply_filter()
        return GLib.SOURCE_REMOVE

    def _save_screenshot(self) -> bool:
        try:
            paintable = Gtk.WidgetPaintable.new(self.window)
            snapshot = Gtk.Snapshot.new()
            width, height = self.window.get_width(), self.window.get_height()
            paintable.snapshot(snapshot, width, height)
            node = snapshot.to_node()
            renderer = self.window.get_native().get_renderer()
            texture = renderer.render_texture(node, Graphene.Rect().init(0, 0, width, height))
            texture.save_to_png(str(self.screenshot))
            log.info("screenshot saved to %s", self.screenshot)
        except Exception:  # noqa: BLE001
            log.exception("screenshot failed")
        self.finish(None)
        return GLib.SOURCE_REMOVE

    # --- filter ---------------------------------------------------------------------------------------------

    def _apply_filter(self) -> None:
        query = self.filter.get_text()
        for card in self.cards:
            card.visible = card.matches(query)
        self.grid.invalidate_filter()
        visible = self._visible_indexes()
        self.nothing.set_visible(not visible)
        if visible and self.active not in visible:
            self._mark(visible[0], reveal=True)

    def _visible_indexes(self) -> list[int]:
        return [c.index for c in self.cards if c.visible]

    # --- interaction ----------------------------------------------------------------------------------------

    def _mark(self, i: int, reveal: bool = False) -> None:
        """Highlight card `i`. With `reveal` (keyboard moves) the scroll follows it; the mouse never scrolls."""
        self.cards[self.active].box.remove_css_class("active")
        self.active = i
        self.cards[i].box.add_css_class("active")
        if reveal:
            GLib.idle_add(self._reveal, i)  # after the layout, so a freshly filtered grid has its final positions

    def _reveal(self, i: int) -> bool:
        viewport = self.scroll.get_child()
        child = self.cards[i].box.get_parent()  # the FlowBoxChild
        if isinstance(viewport, Gtk.Viewport) and child is not None:
            viewport.scroll_to(child, None)
        return GLib.SOURCE_REMOVE

    def _on_pointer(self, _ctl, x: float, y: float) -> None:
        """The first position only records where the pointer rests when the window opens: that is no choice,
        and must not override the preselection. Later positions mark the card under the pointer."""
        first = self._pointer is None
        if self._pointer == (x, y):
            return
        self._pointer = (x, y)
        if first:
            return
        widget = self.window.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None and not widget.has_css_class("card"):
            widget = widget.get_parent()
        if widget is None:
            return
        i = next((c.index for c in self.cards if c.box is widget), None)
        if i is not None and i != self.active:
            self._mark(i)

    def _move(self, step: int, wrap: bool = True) -> None:
        """Move within the visible cards. Left/Right/Tab wrap around; Up/Down stop at the first and last row."""
        visible = self._visible_indexes()
        if not visible:
            return
        pos = visible.index(self.active) if self.active in visible else 0
        target = pos + step
        if wrap:
            target %= len(visible)
        elif not 0 <= target < len(visible):
            return
        self._mark(visible[target], reveal=True)

    def _on_key(self, _ctl, keyval, _keycode, _state) -> bool:
        k = (Gdk.keyval_name(keyval) or "").removeprefix("KP_")  # keypad digits and KP_Enter behave like the others
        filtering = bool(self.filter.get_text())
        if k == "Escape":
            if filtering:
                self.filter.set_text("")
            else:
                self.finish(None)
        elif k in ("Return", "Enter"):
            if self._visible_indexes():
                self.finish(self.active)
        elif k in ("Right", "Tab"):
            self._move(1)
        elif k in ("Left", "ISO_Left_Tab"):
            self._move(-1)
        elif k == "Down":
            self._move(self.columns, wrap=False)
        elif k == "Up":
            self._move(-self.columns, wrap=False)
        elif not filtering and k.isdigit() and 0 < int(k) <= len(self.sources):
            self.finish(int(k) - 1)
        else:
            return False  # anything else (letters, Backspace, digits while filtering) reaches the search entry
        return True

    def _on_signal(self, s) -> bool:
        log.info("signal %s: cancelling", signal.Signals(s).name)
        self.finish(None)
        return GLib.SOURCE_REMOVE

    def finish(self, i: int | None) -> None:
        if self.chosen is None and i is not None:
            self.chosen = self.sources[i].line
        self.quit()


def pick(
    sources: list[Source],
    cfg: Config,
    capturer,
    clients: dict[str, Client],
    preselect: int | None = None,
    screenshot: Path | None = None,
    requesters: list[str] | None = None,
    titles: Callable[[], dict[str, str]] | None = None,
) -> str | None:
    app = Picker(sources, cfg, capturer, clients, preselect, screenshot, requesters, titles)
    app.run([])
    return app.chosen
