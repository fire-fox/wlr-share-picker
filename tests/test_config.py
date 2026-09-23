from pathlib import Path

from wlr_share_picker import config


def test_defaults(clean_env, tmp_path):
    assert config.load(tmp_path / "missing.toml") == config.Config()


def test_toml_with_known_and_unknown_keys(clean_env, tmp_path: Path, caplog):
    path = tmp_path / "config.toml"
    path.write_text("fallback = false\nthumbnail_width = 200\ncolumns = 3\nghost = 1\n")
    cfg = config.load(path)
    assert cfg.fallback is False and cfg.thumbnail_width == 200 and cfg.columns == 3
    assert "ghost" in caplog.text


def test_broken_toml_does_not_raise(clean_env, tmp_path: Path, caplog):
    path = tmp_path / "config.toml"
    path.write_text("this is not = toml =")
    assert config.load(path) == config.Config()
    assert "unreadable" in caplog.text


def test_wrong_types_fall_back_to_defaults(clean_env, tmp_path: Path, caplog):
    path = tmp_path / "config.toml"
    path.write_text(
        'thumbnail_width = "big"\ndmenu = "fuzzel"\nhide_app_ids = "kitty"\nfallback = 1\ncolumns = true\n'
        "max_columns = 4\ncapture_timeout = 3\n[auto]\nrustdesk = 1\n"
    )
    cfg = config.load(path)
    assert cfg.thumbnail_width == 320 and cfg.dmenu == [] and cfg.hide_app_ids == []
    assert cfg.fallback is True and cfg.columns == 0 and cfg.auto == {}
    assert cfg.max_columns == 4 and cfg.capture_timeout == 3  # right types are kept; an int is fine for a float
    for key in ("thumbnail_width", "dmenu", "hide_app_ids", "fallback", "columns", "auto"):
        assert key in caplog.text


def test_example_config_parses_into_the_right_keys(clean_env, tmp_path: Path):
    """Every line of config.example.toml uncommented must land on its own key, not inside [auto] or [colors]."""
    example = Path(__file__).parent.parent / "config.example.toml"
    text = "\n".join(
        line.removeprefix("# ").split("  #")[0].rstrip()
        for line in example.read_text().splitlines()
        if line.startswith("# ") and ("=" in line.split("#")[1] or line.startswith("# ["))
    )
    path = tmp_path / "config.toml"
    path.write_text(text + "\n")
    cfg = config.load(path)
    assert set(cfg.auto) == {"rustdesk"}
    assert "debug" not in cfg.colors and "theme" not in cfg.auto


def test_validate_clamps_values(clean_env, tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('capture_timeout = 0.01\ncapture_threads = 0\njpeg_quality = 500\nfrontend = "odd"\n')
    cfg = config.load(path)
    assert cfg.capture_timeout == 0.5 and cfg.capture_threads == 1 and cfg.jpeg_quality == 100 and cfg.frontend == "auto"


def test_environment_wins(clean_env, monkeypatch, tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('frontend = "gtk"\n')
    monkeypatch.setenv("WLR_SHARE_PICKER_CONFIG", str(path))
    monkeypatch.setenv("WLR_SHARE_PICKER_FRONTEND", "dmenu")
    monkeypatch.setenv("WLR_SHARE_PICKER_DEBUG", "1")
    cfg = config.load()
    assert cfg.frontend == "dmenu" and cfg.debug is True


def test_float_fields_take_floats_and_ints(clean_env, tmp_path: Path):
    """Every float field takes both, whatever its default looks like (reuse_choice_seconds defaults to 90)."""
    floats = [f.name for f in config.fields(config.Config) if f.type is float]
    assert "reuse_choice_seconds" in floats
    path = tmp_path / "config.toml"
    for value in ("0.75", "1"):
        path.write_text("".join(f"{name} = {value}\n" for name in floats))
        cfg = config.load(path)
        assert {name: float(getattr(cfg, name)) for name in floats} == {
            name: float(getattr(config.Config(**{name: float(value)}).validate(), name)) for name in floats
        }
