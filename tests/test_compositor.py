import json
import subprocess

from wlr_share_picker import compositor

MANGO = {
    "clients": [
        {"foreign_toplevel_id": "1F8F", "title": "Roamgate", "appid": "chrome-x__-Profile_1"},
        {"foreign_toplevel_id": "", "title": "no id", "appid": "x"},
        {"title": "no key", "appid": "y"},
    ]
}

SWAY = {
    "type": "root",
    "nodes": [
        {
            "type": "output",
            "nodes": [
                {
                    "type": "workspace",
                    "nodes": [
                        {"type": "con", "app_id": "kitty", "name": "zsh", "foreign_toplevel_identifier": "AA11"},
                        {
                            "type": "con",
                            "app_id": None,
                            "window_properties": {"class": "Teams"},
                            "name": "T",
                            "foreign_toplevel_identifier": "bb22",
                        },
                    ],
                    "floating_nodes": [
                        {"type": "floating_con", "app_id": "zapzap", "name": "W", "foreign_toplevel_identifier": "cc33"}
                    ],
                }
            ],
        }
    ],
}


def _fake_run(output):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(output), stderr="")

    return run


def test_mango_maps_by_lowercase_id(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(MANGO))
    assert compositor.Mango().clients() == {"1f8f": compositor.Client(app_id="chrome-x__-Profile_1", title="Roamgate")}


def test_sway_walks_tree_and_floating_nodes(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(SWAY))
    assert compositor.Sway().clients() == {
        "aa11": compositor.Client(app_id="kitty", title="zsh"),
        "bb22": compositor.Client(app_id="Teams", title="T"),
        "cc33": compositor.Client(app_id="zapzap", title="W"),
    }


def test_detect_from_environment(clean_env, monkeypatch):
    assert compositor.detect().name == "none"
    monkeypatch.setenv("MANGO_INSTANCE_SIGNATURE", "/run/x.sock")
    monkeypatch.setattr(compositor.shutil, "which", lambda b: "/usr/bin/" + b)
    assert compositor.detect().name == "mango"
    monkeypatch.delenv("MANGO_INSTANCE_SIGNATURE")
    monkeypatch.setenv("SWAYSOCK", "/run/s.sock")
    assert compositor.detect().name == "sway"


def test_safe_clients_never_raises(monkeypatch, caplog):
    def explode(*a, **k):
        raise subprocess.TimeoutExpired("mmsg", 2)

    monkeypatch.setattr(subprocess, "run", explode)
    assert compositor.safe_clients(compositor.Mango()) == {}
    assert "mango" in caplog.text
    monkeypatch.setattr(subprocess, "run", _fake_run("neither a dict nor a list"))
    assert compositor.safe_clients(compositor.Mango()) == {}
