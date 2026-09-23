import threading
import time
from pathlib import Path

from compartir_selector import protocol
from compartir_selector.captures import Capturer


def _sources():
    return protocol.parse(["Monitor: DP-1\n", "Window: ok (0a)\n", "Window: hangs (c0e1a)\n", "Window: fails (fa11a)\n"])


def test_capture_one(cfg, fake_grim):
    with Capturer(cfg, grim=fake_grim) as cap:
        path = cap.capture(0, _sources()[0])
        assert path is not None and path.is_file() and path.parent == cap.directory
    assert not cap.directory.exists()


def test_timeout_and_failure_do_not_block_the_rest(cfg, fake_grim):
    results: dict[int, Path | None] = {}
    done = threading.Event()

    def cb(i, path):
        results[i] = path
        if len(results) == 4:
            done.set()

    t0 = time.monotonic()
    with Capturer(cfg, grim=fake_grim) as cap:
        cap.run_all(_sources(), cb)
        assert done.wait(timeout=5)
    assert time.monotonic() - t0 < 4  # the hung one is cut at the timeout (1 s), not after its 10 s sleep
    assert results[0] is not None and results[1] is not None
    assert results[2] is None and results[3] is None


def test_missing_grim(cfg):
    with Capturer(cfg, grim=["/no/such/grim"]) as cap:
        assert not cap.available()
        assert cap.capture(0, _sources()[0]) is None


def test_cleanup_is_idempotent(cfg, fake_grim):
    cap = Capturer(cfg, grim=fake_grim)
    cap.cleanup()
    cap.cleanup()
    assert not cap.directory.exists()


def test_refresh_skips_sources_that_hung_before(cfg, fake_grim):
    seen: list[int] = []
    done = threading.Event()

    def cb(i, _path):
        seen.append(i)
        if len(seen) == 4:
            done.set()

    with Capturer(cfg, grim=fake_grim) as cap:
        cap.run_all(_sources(), cb)
        assert done.wait(timeout=5) and not cap.busy()
        assert cap.timed_out == {"c0e1a"}
        seen.clear()
        again = threading.Event()

        def cb2(i, _path):
            seen.append(i)
            if len(seen) == 3:
                again.set()

        cap.run_all(_sources(), cb2, skip_timed_out=True)
        assert again.wait(timeout=5)
        assert sorted(seen) == [0, 1, 3]


def test_capture_after_cleanup_is_silent(cfg, fake_grim, caplog):
    cap = Capturer(cfg, grim=fake_grim)
    cap.cleanup()
    assert cap.capture(0, _sources()[0]) is None
    assert "grim failed" not in caplog.text


def test_only_captures_the_given_indexes(cfg, fake_grim):
    seen: list[int] = []
    done = threading.Event()

    def cb(i, _path):
        seen.append(i)
        if len(seen) == 2:
            done.set()

    with Capturer(cfg, grim=fake_grim) as cap:
        cap.run_all(_sources(), cb, only={0, 3})
        assert done.wait(timeout=5)
        time.sleep(0.2)  # nothing else may arrive
    assert sorted(seen) == [0, 3]
