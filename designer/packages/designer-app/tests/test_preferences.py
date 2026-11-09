"""Edit ▸ Preferences…, without a window: reading, checking, applying."""

from __future__ import annotations

import pathlib

from designer_model import Session

from designer_app import preferences
from designer_app.state import Settings

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


def test_the_dialog_opens_with_the_current_values():
    settings = Settings(undo_limit=7)
    assert preferences.current(settings) == {
        "undo_limit": "7",
        "autosave_delay_ms": "250",
        "recent_files_limit": "10",
        "contrast": "AA",
    }


def test_the_contrast_level_is_read_as_a_preset_or_a_ratio():
    base = {"undo_limit": "50", "autosave_delay_ms": "250", "recent_files_limit": "5"}
    for typed, kept in (("aaa", "AAA"), (" Max ", "Max"), ("10:1", "10"), ("7", "AAA"), ("12.5", "12.5")):
        values, problem = preferences.check({**base, "contrast": typed})
        assert problem == "" and values["contrast"] == kept, typed


def test_a_contrast_below_aa_is_refused():
    base = {"undo_limit": "50", "autosave_delay_ms": "250", "recent_files_limit": "5"}
    for typed in ("3", "A", "", "22", "nan"):
        values, problem = preferences.check({**base, "contrast": typed})
        assert values == {} and problem.startswith("Minimum contrast must be"), typed


def test_applying_a_contrast_level_stores_its_name():
    settings = Settings()
    preferences.apply({"contrast": "Max"}, settings, Session.open(EXAMPLE).stack)
    assert settings.contrast == "Max"


def test_good_values_come_back_as_numbers():
    values, problem = preferences.check({"undo_limit": " 50 ", "autosave_delay_ms": "1_000", "recent_files_limit": "5"})
    assert problem == ""
    assert values == {"undo_limit": 50, "autosave_delay_ms": 1000, "recent_files_limit": 5}


def test_a_word_is_not_a_number():
    values, problem = preferences.check({"undo_limit": "lots", "autosave_delay_ms": "250", "recent_files_limit": "5"})
    assert values == {}
    assert problem == "Undo steps kept must be a whole number"


def test_a_value_out_of_range_names_the_range():
    _, problem = preferences.check({"undo_limit": "50", "autosave_delay_ms": "250", "recent_files_limit": "500"})
    assert problem == "Recent files listed must be between 1 and 50"


def test_applying_takes_effect_now():
    settings = Settings(recent_files=[f"/m/{n}.json" for n in range(8)])
    session = Session.open(EXAMPLE)
    preferences.apply({"undo_limit": 3, "autosave_delay_ms": 900, "recent_files_limit": 2}, settings, session.stack)
    assert (settings.undo_limit, settings.autosave_delay_ms, settings.recent_files_limit) == (3, 900, 2)
    assert settings.recent_files == ["/m/0.json", "/m/1.json"]
    assert session.stack.limit == 3


def test_every_preference_is_a_setting_that_exists():
    assert all(p.key in Settings.__dataclass_fields__ for p in preferences.PREFERENCES)
