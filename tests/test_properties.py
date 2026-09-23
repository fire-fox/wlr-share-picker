"""Property-based tests (Hypothesis) on everything that takes outside input: the portal's lines, window titles,
the dmenu's answer, the config file, /proc and the memories. The key promise: the answer is always a line the
portal sent (or that same window with its current title), never something made up."""

import json
import string
import tempfile
from pathlib import Path
from unittest import mock

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from compartir_selector import config, protocol, recent, requester, search, ui_dmenu  # noqa: E402
from compartir_selector.config import Config  # noqa: E402

LINE_TEXT = st.text(alphabet=st.characters(blacklist_characters="\n\r"), max_size=80)
IDENT = st.text(alphabet=string.ascii_letters + string.digits + "-_.:", min_size=1, max_size=32)
OUTPUT = st.text(alphabet=string.ascii_letters + string.digits + "-", min_size=1, max_size=12)
WINDOW = st.builds(lambda title, ident: f"Window: {title} ({ident})\n", LINE_TEXT, IDENT)
MONITOR = st.builds(lambda name, desc: f"Monitor: {name} {desc}\n", OUTPUT, LINE_TEXT)
PORTAL_LINES = st.lists(st.one_of(WINDOW, MONITOR, LINE_TEXT.map(lambda t: t + "\n")), max_size=12)
SETTINGS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


@SETTINGS
@given(st.lists(st.text(max_size=120), max_size=20))
def test_parse_never_raises_and_only_keeps_given_lines(lines):
    for source in protocol.parse(lines):
        assert source.line in lines


@SETTINGS
@given(LINE_TEXT, IDENT)
def test_window_lines_round_trip(title, ident):
    source = protocol.parse_line(f"Window: {title} ({ident})\n")
    assert source is not None and not source.is_monitor
    assert (source.name, source.raw_id, source.id) == (title, ident, ident.lower())
    assert source.grim_args() == ["-T", ident]


@SETTINGS
@given(OUTPUT, LINE_TEXT)
def test_monitor_lines_round_trip(name, description):
    source = protocol.parse_line(f"Monitor: {name} {description}\n")
    assert source is not None and source.is_monitor
    assert (source.id, source.description) == (name, description.strip())
    assert source.grim_args() == ["-o", name]


@SETTINGS
@given(LINE_TEXT, IDENT, st.dictionaries(st.text(max_size=10), LINE_TEXT, max_size=4), LINE_TEXT)
def test_refresh_title_only_ever_renames_the_same_window(title, ident, others, current):
    line = f"Window: {title} ({ident})\n"
    answer = protocol.refresh_title(line, {**others, ident.lower(): current})
    if not current or current == title:
        assert answer == line
    else:
        assert answer == f"Window: {current} ({ident})\n"
    assert protocol.parse_line(answer).raw_id == ident


@SETTINGS
@given(PORTAL_LINES, st.text(max_size=200))
def test_the_dmenu_can_never_make_up_an_answer(lines, typed):
    """A dmenu that accepts free text returns anything: only a line the portal sent may come out."""
    reply = mock.Mock(stdout=typed, returncode=0)
    with mock.patch.object(ui_dmenu.subprocess, "run", return_value=reply):
        answer = ui_dmenu.pick(lines, Config(dmenu=["true"]))
    assert answer is None or answer.rstrip("\r\n") in {line.rstrip("\r\n") for line in lines}


@SETTINGS
@given(PORTAL_LINES, st.lists(st.text(max_size=12), max_size=4), st.lists(st.text(max_size=12), max_size=4))
def test_exclude_never_hides_monitors_or_everything(lines, hide_ids, hide_titles):
    sources = protocol.parse(lines)
    app_ids = {s.id: s.name[:8] for s in sources if not s.is_monitor}
    kept = protocol.exclude(sources, app_ids, hide_ids, hide_titles)
    assert [s for s in sources if s.is_monitor] == [s for s in kept if s.is_monitor]
    assert all(s in sources for s in kept)
    assert bool(kept) == bool(sources)


@SETTINGS
@given(
    PORTAL_LINES,
    st.dictionaries(
        st.sampled_from(["kind", "id", "time", "requester_pid", "x"]),
        st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), st.text(max_size=12)),
        max_size=5,
    ),
    st.integers(0, 3),
)
def test_recall_only_answers_with_a_listed_source_for_the_same_process(lines, record, pid):
    sources = protocol.parse(lines)
    with tempfile.TemporaryDirectory() as run, mock.patch.dict("os.environ", {"XDG_RUNTIME_DIR": run}):
        target = Path(run) / "compartir-selector"
        target.mkdir(mode=0o700)
        (target / recent.FILE_NAME).write_text(json.dumps(record))
        answer = recent.recall(sources, Config(reuse_choice_seconds=90), now=100.0, requester_pid=pid)
    if answer is not None:
        assert answer in sources
        assert int(record.get("requester_pid") or 0) == pid


def _toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)} = {_toml(v)}" for k, v in value.items()) + "}"


SCALAR = st.one_of(
    st.booleans(), st.integers(-(2**63), 2**63 - 1), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=20)
)
VALUE = st.one_of(SCALAR, st.lists(SCALAR, max_size=4), st.dictionaries(st.text(max_size=8), SCALAR, max_size=4))


@SETTINGS
@given(st.dictionaries(st.sampled_from([f.name for f in config.fields(Config)]), VALUE, max_size=10))
def test_any_config_file_loads_into_a_valid_config(values):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.toml"
        path.write_text("".join(f"{key} = {_toml(value)}\n" for key, value in values.items()), encoding="utf-8")
        cfg = config.load(path, env={})
    assert cfg.frontend in ("auto", "gtk", "dmenu") and cfg.theme in ("auto", "dark", "light")
    assert 120 <= cfg.thumbnail_width <= 1920 and 0 <= cfg.columns <= 24 and 1 <= cfg.max_columns <= 24
    assert 1 <= cfg.capture_threads <= 32 and 0.5 <= cfg.capture_timeout <= 60 and 1 <= cfg.jpeg_quality <= 100
    assert 0.05 <= cfg.monitor_scale <= 1 and 0.05 <= cfg.window_scale <= 1 and 0 <= cfg.reuse_choice_seconds <= 86400
    assert cfg.refresh_seconds == 0 or 0.5 <= cfg.refresh_seconds <= 3600
    for name in ("dmenu", "hide_app_ids", "hide_titles"):
        assert all(isinstance(v, str) for v in getattr(cfg, name))
    for name in ("auto", "colors"):
        assert all(isinstance(v, str) for v in getattr(cfg, name).values())


@SETTINGS
@given(LINE_TEXT)
def test_every_word_of_a_title_finds_it(title):
    for word in title.split():
        assert search.matches(word, title)


@SETTINGS
@given(st.text(max_size=300))
def test_cgroup_parsing_never_raises(text):
    result = requester.app_id_from_cgroup(text)
    assert result is None or (isinstance(result, str) and result)
