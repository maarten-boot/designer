"""Application state.

No tkinter here, deliberately: where settings live and how they survive damage
is testable without a display, and it is the part most likely to break on a
platform nobody develops on.
"""

from __future__ import annotations

import json

import pytest

from designer_app.state import COLUMNS, TITLES, Settings, config_dir


def test_config_dir_follows_the_platform(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_dir() == tmp_path / "designer"


def test_config_dir_falls_back_without_xdg(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert config_dir() == tmp_path / ".config" / "designer"


def test_config_dir_on_windows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config_dir() == tmp_path / "Designer"


def test_config_dir_on_macos(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert config_dir() == tmp_path / "Library" / "Application Support" / "Designer"


def test_settings_round_trip(tmp_path) -> None:
    settings = Settings(show_builtins=True, column_widths={"entity": 240})
    settings.save(tmp_path)
    assert Settings.load(tmp_path).show_builtins is True
    assert Settings.load(tmp_path).column_widths == {"entity": 240}


def test_missing_settings_gives_defaults(tmp_path) -> None:
    assert Settings.load(tmp_path).undo_limit == 100


def test_corrupt_settings_are_never_fatal(tmp_path) -> None:
    (tmp_path / "settings.json").write_text("{ not json at all")
    assert Settings.load(tmp_path).undo_limit == 100


def test_unknown_keys_are_ignored(tmp_path) -> None:
    """A file written by a newer build must still open."""
    (tmp_path / "settings.json").write_text(json.dumps({"undo_limit": 7, "from_the_future": True}))
    assert Settings.load(tmp_path).undo_limit == 7


def test_stale_column_names_are_dropped(tmp_path) -> None:
    (tmp_path / "settings.json").write_text(json.dumps({"collapsed_columns": ["entity", "gone"]}))
    assert Settings.load(tmp_path).collapsed_columns == ["entity"]


def test_settings_are_written_atomically(tmp_path) -> None:
    Settings().save(tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_recent_files_are_most_recent_first(tmp_path) -> None:
    settings = Settings()
    for name in ("a.json", "b.json", "c.json"):
        settings.remember(tmp_path / name)
    assert [p.split("/")[-1] for p in settings.recent_files] == ["c.json", "b.json", "a.json"]
    assert settings.last_file.endswith("c.json")


def test_reopening_a_file_moves_it_to_the_front(tmp_path) -> None:
    settings = Settings()
    settings.remember(tmp_path / "a.json")
    settings.remember(tmp_path / "b.json")
    settings.remember(tmp_path / "a.json")
    assert len(settings.recent_files) == 2
    assert settings.recent_files[0].endswith("a.json")


def test_recent_files_are_capped(tmp_path) -> None:
    settings = Settings(recent_files_limit=3)
    for i in range(10):
        settings.remember(tmp_path / f"{i}.json")
    assert len(settings.recent_files) == 3


def test_a_missing_file_is_kept_and_marked(tmp_path) -> None:
    """A disconnected share should not erase history."""
    present = tmp_path / "here.json"
    present.write_text("{}")
    settings = Settings()
    settings.remember(present)
    settings.remember(tmp_path / "gone.json")
    marked = dict((p.split("/")[-1], ok) for p, ok in settings.recent())
    assert marked == {"gone.json": False, "here.json": True}


@pytest.mark.parametrize("column", COLUMNS)
def test_every_column_can_be_collapsed(column) -> None:
    settings = Settings(collapsed_columns=[column])
    assert settings.collapsed_columns == [column]


def test_column_order_runs_from_primitives_to_deliverable() -> None:
    """Pinned, because the order carries meaning and is easy to disturb.

    A Context scopes everything; Types and Validators are the primitives; a
    Property is a Type given a name; an Entity is Properties given a shape; a
    Schema is the deliverable. Beginning at the Schema would begin at the end.
    """
    assert COLUMNS == ("context", "type", "validator", "property", "entity", "schema")


def test_titles_and_columns_agree() -> None:
    """The window builds its columns from COLUMNS and labels them from TITLES,
    so the two must not drift."""
    assert tuple(TITLES) == COLUMNS
    assert all(TITLES[name] for name in COLUMNS)
