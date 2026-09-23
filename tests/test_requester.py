import logging
from pathlib import Path

from compartir_selector import protocol, requester

CG = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/{unit}\n"


def test_app_id_from_cgroup_variants():
    f = requester.app_id_from_cgroup
    assert f(CG.format(unit="app-org.chromium.Chromium-16966.scope")) == "org.chromium.Chromium"
    assert f(CG.format(unit="app-teams-trabajo-5246.scope")) == "teams-trabajo"
    assert f(CG.format(unit="app-flatpak-org.mozilla.firefox-1234.scope")) == "org.mozilla.firefox"
    assert f(CG.format(unit="app-gnome-org.gnome.Nautilus-4321.scope")) == "org.gnome.Nautilus"
    assert f(CG.format(unit="app-dbus-org.kde.dolphin@abc.service")) == "org.kde.dolphin"
    assert f(CG.format(unit="app-teams\\x2dpersonal-77.scope")) == "teams-personal"
    assert f(CG.format(unit="session-2.scope")) is None
    assert f("") is None


def test_matches_desktop_id_last_segment_or_comm():
    r = requester.Requester(app_id="org.chromium.Chromium", comm="chromium", pid=1, path="p")
    assert r.matches("chromium") and r.matches("ORG.chromium.Chromium") and r.matches("Chromium")
    assert not r.matches("firefox")


def test_describe_falls_back_to_comm(tmp_path: Path):
    (tmp_path / "42").mkdir()
    (tmp_path / "42" / "comm").write_text("sunshine\n")
    (tmp_path / "42" / "cgroup").write_text("0::/user.slice/user-1000.slice/session-2.scope\n")
    r = requester.describe(42, "p", proc=tmp_path)
    assert (r.app_id, r.comm, r.pid) == ("sunshine", "sunshine", 42)
    assert requester.describe(99, "p", proc=tmp_path).app_id == ""


def test_detect_prefers_new_sessions_and_dedupes_pids(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    proc = tmp_path / "proc"
    for pid, comm, unit in ((10, "teams", "app-teams-trabajo-10.scope"), (20, "chromium", "app-org.chromium.Chromium-20.scope")):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "comm").write_text(comm)
        (proc / str(pid) / "cgroup").write_text(CG.format(unit=unit))
    root = requester.SESSIONS_ROOT
    pids = {"1_10": 10, "1_20": 20}
    first = [f"{root}/1_10/a"]
    got = requester.detect(sessions=lambda bus: first, pid_lookup=lambda bus, s: pids[s], proc=proc, connect=lambda: None)
    assert [r.app_id for r in got] == ["teams-trabajo"]
    # Teams keeps sharing; Chromium asks twice (two sessions, same sender): only Chromium is the requester now
    later = [f"{root}/1_10/a", f"{root}/1_20/b", f"{root}/1_20/c"]
    got = requester.detect(sessions=lambda bus: later, pid_lookup=lambda bus, s: pids[s], proc=proc, connect=lambda: None)
    assert [(r.app_id, r.pid) for r in got] == [("org.chromium.Chromium", 20)]
    # nothing new: every live session is a candidate
    got = requester.detect(sessions=lambda bus: later, pid_lookup=lambda bus, s: pids[s], proc=proc, connect=lambda: None)
    assert sorted(r.app_id for r in got) == ["org.chromium.Chromium", "teams-trabajo"]


def test_detect_never_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    def boom(bus):
        raise RuntimeError("no bus")

    assert requester.detect(sessions=boom, connect=lambda: None) == []

    def no_bus():
        raise RuntimeError("no session bus")

    assert requester.detect(connect=no_bus) == []


def test_auto_choice_monitor_then_window_app(caplog):
    sources = protocol.parse(["Monitor: DP-1 ASUS\n", "Window: a (0a)\n", "Window: b (0b)\n"])
    app_ids = {"0a": "kitty", "0b": "chromium"}
    sun = requester.Requester(app_id="sunshine", comm="sunshine", pid=5, path="p")
    assert requester.auto_choice([sun], sources, app_ids, {"sunshine": "dp-1"}).id == "DP-1"
    assert requester.auto_choice([sun], sources, app_ids, {"sunshine": "chromium"}).id == "0b"
    assert requester.auto_choice([sun], sources, app_ids, {"rustdesk": "DP-1"}) is None
    assert requester.auto_choice([], sources, app_ids, {"sunshine": "DP-1"}) is None
    assert requester.auto_choice([sun], sources, app_ids, {"sunshine": "HDMI-A-1"}) is None
    assert "no such monitor" in caplog.text


def test_auto_choice_needs_an_unambiguous_requester(caplog):
    """RustDesk sharing and Chromium asking with no new session to tell them apart: no silent answer."""
    caplog.set_level(logging.INFO)
    sources = protocol.parse(["Monitor: DP-1 ASUS\n"])
    rust = requester.Requester(app_id="rustdesk", comm="rustdesk", pid=5, path="a")
    chromium = requester.Requester(app_id="org.chromium.Chromium", comm="chromium", pid=6, path="b")
    assert requester.auto_choice([rust, chromium], sources, {}, {"rustdesk": "DP-1"}) is None
    assert "cannot tell" in caplog.text
