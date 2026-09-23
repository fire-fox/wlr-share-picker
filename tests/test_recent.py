from compartir_selector import protocol, recent
from compartir_selector.config import Config

LINES = ["Monitor: DP-1 ASUS\n", "Window: Roamgate - tab one (1f8f)\n"]


def _sources(lines=LINES):
    return protocol.parse(lines)


def test_recall_matches_window_by_id_even_if_title_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recent.remember("Window: Roamgate - tab one (1f8f)\n", now=1000.0)
    later = _sources(["Monitor: DP-1 ASUS\n", "Window: Roamgate - tab two (1F8F)\n"])
    got = recent.recall(later, Config(reuse_choice_seconds=20), now=1010.0)
    assert got is not None and got.line == "Window: Roamgate - tab two (1F8F)\n"


def test_recall_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recent.remember(LINES[0], now=1000.0)
    assert recent.recall(_sources(), Config(reuse_choice_seconds=20), now=1021.0) is None
    assert recent.recall(_sources(), Config(reuse_choice_seconds=20), now=999.0) is None  # clock went backwards


def test_recall_off_or_missing_source(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recent.remember(LINES[1], now=1000.0)
    assert recent.recall(_sources(), Config(reuse_choice_seconds=0), now=1001.0) is None
    assert recent.recall(_sources([LINES[0]]), Config(reuse_choice_seconds=20), now=1001.0) is None


def test_remember_ignores_garbage_and_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recent.remember("not a portal line\n")
    assert not (tmp_path / "compartir-selector" / recent.FILE_NAME).exists()
    recent.remember(LINES[0])
    path = tmp_path / "compartir-selector" / recent.FILE_NAME
    assert path.stat().st_mode & 0o777 == 0o600
    recent.forget()
    assert not path.exists()
    recent.forget()  # idempotent


def test_preferred_by_id_then_by_app_id(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    recent.remember("Window: Roamgate (1f8f)\n", app_id="chromium")
    sources = _sources(["Monitor: DP-1\n", "Window: other (aa)\n", "Window: Roamgate (1f8f)\n"])
    assert recent.preferred(sources, {}) == 2
    restarted = _sources(["Monitor: DP-1\n", "Window: other (aa)\n", "Window: Roamgate again (bb)\n"])
    assert recent.preferred(restarted, {"bb": "chromium", "aa": "kitty"}) == 2
    assert recent.preferred(restarted, {"bb": "firefox"}) is None
    assert (tmp_path / "state" / "compartir-selector" / recent.FILE_NAME).is_file()


def test_remember_can_skip_the_persistent_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    recent.remember("Monitor: DP-1\n", persistent=False)
    assert (tmp_path / "run" / "compartir-selector" / recent.FILE_NAME).is_file()
    assert not (tmp_path / "state").exists()


def test_recall_is_bound_to_the_requesting_process(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recent.remember(LINES[1], now=1000.0, requester_pid=500)
    cfg = Config(reuse_choice_seconds=90)
    assert recent.recall(_sources(), cfg, now=1010.0, requester_pid=500) is not None  # same app asks again
    assert recent.recall(_sources(), cfg, now=1010.0, requester_pid=0) is None  # unknown requester: dialog
    assert recent.recall(_sources(), cfg, now=1010.0, requester_pid=777) is None  # another app never inherits it
    recent.remember(LINES[1], now=1000.0)  # chooser did not know who asked either
    assert recent.recall(_sources(), cfg, now=1010.0, requester_pid=0) is not None  # blind matches blind: time only
    assert recent.recall(_sources(), cfg, now=1010.0, requester_pid=777) is None


def test_recall_survives_a_corrupt_record(tmp_path, monkeypatch):
    """Found by the property tests: JSON accepts Infinity, and int(inf) raises OverflowError."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    directory = tmp_path / "compartir-selector"
    directory.mkdir(mode=0o700)
    for record in (
        '{"kind": "monitor", "id": "DP-1", "time": 1000, "requester_pid": Infinity}',
        '{"kind": "monitor", "id": "DP-1", "time": NaN}',
        "[1, 2]",
        '"text"',
    ):
        (directory / recent.FILE_NAME).write_text(record)
        assert recent.recall(_sources(), Config(reuse_choice_seconds=90), now=1001.0) is None
