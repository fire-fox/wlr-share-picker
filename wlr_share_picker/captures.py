"""Thumbnails with grim: one per source, with bounded parallelism and a hard time limit.

A window already being shared through the portal hangs `grim -T` (observed with Chromium): that is why every
capture has a timeout and the others never wait for it. Files go to a temporary directory removed on exit,
also on SIGTERM/SIGINT.
"""

import atexit
import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import logs
from .config import Config
from .protocol import Source

log = logs.get("captures")

Callback = Callable[[int, Path | None], None]


class Capturer:
    def __init__(self, cfg: Config, grim: list[str] | None = None):
        self.cfg = cfg
        self.grim = grim or ["grim"]
        self.directory = Path(tempfile.mkdtemp(prefix="wlr-share-picker-"))
        self._pool: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._in_flight = 0
        self.timed_out: set[str] = set()  # source ids whose grim hung: not retried on refresh
        self.closed = False
        atexit.register(self.cleanup)

    def busy(self) -> bool:
        with self._lock:
            return self._in_flight > 0

    def available(self) -> bool:
        return shutil.which(self.grim[0]) is not None

    def capture(self, index: int, source: Source) -> Path | None:
        """Capture one source to a downscaled JPEG. `None` if grim fails or hangs, or after cleanup."""
        if self.closed:
            return None
        target = self.directory / f"{index}.jpg"
        scale = self.cfg.monitor_scale if source.is_monitor else self.cfg.window_scale
        cmd = [*self.grim, "-s", str(scale), "-t", "jpeg", "-q", str(self.cfg.jpeg_quality), *source.grim_args(), str(target)]
        try:
            # Own session: on timeout the whole process group is killed, not just the parent (otherwise an
            # orphaned child holding the pipe open would keep this capture waiting until it exits).
            # S603: an argument list, no shell; the only outside input is the portal's output name or toplevel id.
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, start_new_session=True)  # noqa: S603
        except OSError as e:
            log.warning("could not run grim: %s", e)
            return None
        try:
            _, err = proc.communicate(timeout=self.cfg.capture_timeout)
        except subprocess.TimeoutExpired:
            log.info("grim exceeded %.1fs on %s %r (already being shared?)", self.cfg.capture_timeout, source.kind, source.name)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            self.timed_out.add(source.id)
            return None
        if proc.returncode != 0 or not target.is_file():
            if not self.closed:  # a refresh racing with cleanup is not worth a log line
                log.info("grim failed on %s %r: %s", source.kind, source.name, (err or "").strip())
            return None
        return target

    def run_all(
        self, sources: Iterable[Source], callback: Callback, skip_timed_out: bool = False, only: set[int] | None = None
    ) -> None:
        """Queue every capture with at most `capture_threads` running at once. `callback` runs on the capture thread.
        With `skip_timed_out`, sources whose grim hung before are left alone (their card keeps its last state);
        with `only`, just those indexes are captured (the cards the filter leaves visible)."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=self.cfg.capture_threads, thread_name_prefix="grim")
        for i, source in enumerate(sources):
            if only is not None and i not in only:
                continue
            if skip_timed_out and source.id in self.timed_out:
                continue
            with self._lock:
                self._in_flight += 1
            self._pool.submit(self._one, i, source, callback)

    def _one(self, i: int, source: Source, callback: Callback) -> None:
        try:
            callback(i, self.capture(i, source))
        except Exception:  # noqa: BLE001 — one failing thumbnail must not kill the thread silently
            log.exception("error capturing %s %r", source.kind, source.name)
            callback(i, None)
        finally:
            with self._lock:
                self._in_flight -= 1

    def cleanup(self) -> None:
        """Idempotent. Does not wait for a hung grim: pool threads are abandoned and the process exits anyway."""
        self.closed = True
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        if self.directory.exists():
            shutil.rmtree(self.directory, ignore_errors=True)
            log.debug("temporary files removed: %s", self.directory)

    def __enter__(self) -> "Capturer":
        return self

    def __exit__(self, *_) -> None:
        self.cleanup()
