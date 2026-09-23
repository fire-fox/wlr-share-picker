from wlr_share_picker import protocol


def test_monitor_with_description():
    s = protocol.parse_line("Monitor: DP-1 ASUSTek COMPUTER INC PA34VCNV\n")
    assert s is not None and s.is_monitor
    assert (s.id, s.name, s.description) == ("DP-1", "DP-1", "ASUSTek COMPUTER INC PA34VCNV")
    assert s.grim_args() == ["-o", "DP-1"]
    assert s.line.endswith("\n")


def test_monitor_without_description():
    s = protocol.parse_line("Monitor: HDMI-A-1")
    assert s is not None and s.description == ""


def test_window_with_parentheses_in_title():
    s = protocol.parse_line("Window: Roamgate (dev) - Chromium (1F8F762D1254178A8AEF401C0EBB4D0F)\n")
    assert s is not None and not s.is_monitor
    assert s.name == "Roamgate (dev) - Chromium"
    assert s.id == "1f8f762d1254178a8aef401c0ebb4d0f"  # lookup key
    assert s.grim_args() == ["-T", "1F8F762D1254178A8AEF401C0EBB4D0F"]  # grim gets it verbatim


def test_window_id_is_opaque_not_only_hex():
    s = protocol.parse_line("Window: Editor (win-42_Z)\n")
    assert s is not None and (s.name, s.id, s.raw_id) == ("Editor", "win-42_z", "win-42_Z")
    assert s.grim_args() == ["-T", "win-42_Z"]
    assert protocol.parse_line("Window: no id ()\n") is None


def test_invalid_line_is_skipped_without_failing():
    assert protocol.parse_line("Garbage without format") is None
    sources = protocol.parse(["Garbage\n", "Window: no id\n", "\n", "Monitor: DP-1\n"])
    assert [s.id for s in sources] == ["DP-1"]


def test_monitors_first_and_stable_order():
    sources = protocol.parse(["Window: b (0b)\n", "Window: a (0a)\n", "Monitor: DP-2\n", "Monitor: DP-1\n"])
    assert [s.id for s in sources] == ["DP-2", "DP-1", "0b", "0a"]


def test_returned_line_is_identical_to_the_received_one():
    original = "Window: Title with ñ and  odd   spaces (abc123)\n"
    s = protocol.parse_line(original)
    assert s is not None and s.line is original


def test_exclude_by_app_id_and_title_but_never_monitors():
    sources = protocol.parse(["Monitor: DP-1\n", "Window: Teams call (0a)\n", "Window: Roamgate (0b)\n", "Window: herdr (0c)\n"])
    kept = protocol.exclude(sources, {"0c": "herdr", "0a": "teams-trabajo"}, ["HERDR"], ["teams"])
    assert [s.id for s in kept] == ["DP-1", "0b"]


def test_exclude_never_hides_everything(caplog):
    sources = protocol.parse(["Window: Roamgate (0b)\n"])
    assert protocol.exclude(sources, {"0b": "chromium"}, ["chromium"], []) == sources
    assert "hide every source" in caplog.text


def test_refresh_title_only_when_it_changed():
    line = "Window: (19) Calendar | Teams (8036)\n"
    assert protocol.refresh_title(line, {}) == line
    assert protocol.refresh_title(line, {"8036": "(19) Calendar | Teams"}) == line
    assert protocol.refresh_title(line, {"8036": "(20) Calendar | Teams"}) == "Window: (20) Calendar | Teams (8036)\n"
    assert protocol.refresh_title("Monitor: DP-1\n", {"x": "y"}) == "Monitor: DP-1\n"
    assert protocol.refresh_title("garbage\n", {}) == "garbage\n"


def test_refresh_title_keeps_the_id_verbatim():
    line = "Window: old (8036AB)\n"
    assert protocol.refresh_title(line, {"8036ab": "new"}) == "Window: new (8036AB)\n"
