from wlr_share_picker import ui_dmenu
from wlr_share_picker.config import Config

LINES = ["Monitor: DP-1 ASUS\n", "Window: Roamgate (1f8f)\n"]


def test_picks_a_valid_line(fake_dmenu, monkeypatch):
    monkeypatch.setenv("DMENU_PICK", "2")
    assert ui_dmenu.pick(LINES, Config(dmenu=[str(fake_dmenu)])) == LINES[1]


def test_cancel(fake_dmenu, monkeypatch):
    monkeypatch.delenv("DMENU_PICK", raising=False)
    assert ui_dmenu.pick(LINES, Config(dmenu=[str(fake_dmenu)])) is None


def test_made_up_line_is_rejected(tmp_path, caplog):
    liar = tmp_path / "dmenu"
    liar.write_text("#!/bin/sh\necho 'Window: made up (00)'\n")
    liar.chmod(0o755)
    assert ui_dmenu.pick(LINES, Config(dmenu=[str(liar)])) is None
    assert "not in the list" in caplog.text


def test_no_dmenu_installed(monkeypatch, caplog):
    monkeypatch.setattr(ui_dmenu.shutil, "which", lambda _: None)
    assert ui_dmenu.command(Config()) is None
    assert ui_dmenu.pick(LINES, Config()) is None
    assert "cancelling" in caplog.text
