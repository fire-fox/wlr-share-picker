import pytest

from compartir_selector import icons


def test_candidates_without_app_id():
    assert icons.candidates("") == []


def test_candidates_chromium_profile():
    c = icons.candidates("chrome-127.0.0.2__-Profile_1")
    assert c[0] == "chrome-127.0.0.2__-Profile_1" and "chromium" in c


def test_candidates_reverse_dns_and_alias_without_duplicates():
    assert icons.candidates("org.kde.dolphin") == ["org.kde.dolphin", "dolphin", "system-file-manager"]
    assert icons.candidates("org.chromium.Chromium") == ["org.chromium.Chromium", "Chromium", "chromium", "org.chromium.chromium"]


def test_resolve_never_raises():
    pytest.importorskip("gi")
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio

    assert isinstance(icons.resolve("app-id-that-does-not-exist-xyz"), Gio.Icon)
    assert isinstance(icons.resolve("", True), Gio.Icon)
    assert icons.resolve("", True).to_string() == icons.MONITOR_ICON


def test_app_name_falls_back_to_the_app_id():
    pytest.importorskip("gi")
    assert icons.app_name("") == ""
    assert icons.app_name("app-id-that-does-not-exist-xyz") == "app-id-that-does-not-exist-xyz"
