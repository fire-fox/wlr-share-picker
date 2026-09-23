from pathlib import Path

from wlr_share_picker import theme


def test_define_colors_follows_imports(tmp_path: Path):
    (tmp_path / "colors.css").write_text("@define-color accent_bg_color #ffb866;\n@define-color window_bg_color #131313;\n")
    (tmp_path / "gtk.css").write_text('@import url("colors.css");\n@define-color window_fg_color #e2e2e2;\n')
    colors = theme.define_colors(tmp_path / "gtk.css")
    assert colors == {"accent_bg_color": "#ffb866", "window_bg_color": "#131313", "window_fg_color": "#e2e2e2"}


def test_missing_file_gives_empty(tmp_path: Path):
    assert theme.define_colors(tmp_path / "nope.css") == {}


def test_from_gtk_requires_the_two_key_colors():
    assert theme.from_gtk({"accent_bg_color": "#f00"}, theme.DARK) == theme.DARK
    p = theme.from_gtk({"accent_bg_color": "#f00", "window_bg_color": "#000", "card_bg_color": "#111"}, theme.DARK)
    assert (p.accent, p.background, p.card, p.text) == ("#f00", "#000", "#111", theme.DARK.text)


def test_build_presets_and_overrides(tmp_path: Path, caplog):
    p = theme.build("light", {"accent": "#123456", "bogus": "x"}, tmp_path)
    assert p.accent == "#123456" and p.background == theme.LIGHT.background
    assert "bogus" in caplog.text
    assert theme.build("dark", {}, tmp_path) == theme.DARK


def test_css_uses_the_palette():
    css = theme.css(theme.LIGHT).decode()
    assert theme.LIGHT.accent in css and ".card.active" in css
