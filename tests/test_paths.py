"""Private directories and files: what a planted directory, symlink or file can and cannot do."""

import json
import os
import stat
import tempfile

import pytest

from wlr_share_picker import paths, protocol, recent, requester
from wlr_share_picker.config import Config

MONITOR = ["Monitor: DP-1\n"]


def test_without_runtime_dir_the_short_memory_is_off_and_nothing_goes_to_tmp(tmp_path, monkeypatch):
    shared_tmp = tmp_path / "tmp"
    shared_tmp.mkdir()
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(tempfile, "tempdir", str(shared_tmp))
    recent.remember(MONITOR[0], now=1000.0)
    assert paths.runtime_dir() is None
    assert recent.recall(protocol.parse(MONITOR), Config(), now=1001.0) is None
    assert not any(shared_tmp.iterdir())


def test_a_directory_planted_as_a_symlink_is_refused(tmp_path, monkeypatch, caplog):
    """Someone prepares the directory to answer for us: a fresh «last choice» would share DP-1 without a dialog."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / recent.FILE_NAME).write_text(json.dumps({"kind": "monitor", "id": "DP-1", "time": 1000.0, "requester_pid": 0}))
    run = tmp_path / "run"
    run.mkdir()
    (run / paths.APP).symlink_to(planted)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    assert paths.runtime_dir() is None
    assert recent.recall(protocol.parse(MONITOR), Config(), now=1001.0) is None
    assert "not a directory owned by this user" in caplog.text


def test_own_directory_with_loose_permissions_is_tightened(tmp_path, monkeypatch):
    loose = tmp_path / "run" / paths.APP
    loose.mkdir(parents=True)
    loose.chmod(0o755)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    assert paths.runtime_dir() == loose
    assert stat.S_IMODE(loose.stat().st_mode) == 0o700


def test_files_are_private_from_the_start_and_atomic(tmp_path):
    target = tmp_path / "x.json"
    paths.write_json(target, {"a": 1})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert paths.read_json(target) == {"a": 1}
    assert not target.with_suffix(".tmp").exists()


def test_writing_never_follows_a_planted_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep")
    target = tmp_path / "x.json"
    target.with_suffix(".tmp").symlink_to(victim)
    with pytest.raises(OSError):
        paths.write_json(target, {"a": 1})
    assert victim.read_text() == "keep"


def test_unreadable_or_foreign_json_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    directory = paths.runtime_dir()
    (directory / recent.FILE_NAME).write_text("not json")
    (directory / requester.SEEN_FILE).write_text(json.dumps([1, "/a", None]))
    assert recent.recall(protocol.parse(MONITOR), Config(), now=1.0) is None
    assert requester._load_seen() == {"/a"}
    assert os.stat(directory).st_uid == os.getuid()
