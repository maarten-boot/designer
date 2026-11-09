"""The colours and the contrast they must reach, without a display.

The guarantee: at any level from AA to Max, every foreground the application
draws reaches the minimum ratio against every background it can be drawn on.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from designer_app import palette

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_app"
LEVELS = ["AA", "AAA", "Max", 5, 8.5, 10, 14, 17.5, 18, 19, 20, 20.5]


def test_the_ratio_matches_the_wcag_reference_values() -> None:
    assert palette.ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert palette.ratio("#ffffff", "#ffffff") == pytest.approx(1.0)
    # #767676 is the well-known lightest grey that passes AA on white
    assert palette.ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)
    assert palette.ratio("#777777", "#ffffff") < 4.5
    assert palette.ratio("#a01b0b", "#ffffff") == palette.ratio("#ffffff", "#a01b0b")


@pytest.mark.parametrize("level", LEVELS)
def test_every_pair_reaches_the_minimum(level) -> None:
    resolved = palette.resolve(level)
    failing = [
        f"{name}: {palette.ratio(fg, bg):.2f}"
        for name, fg, bg in resolved.pairs()
        if not palette.meets(fg, bg, resolved.minimum)
    ]
    assert failing == []


def test_the_default_is_black_on_white_at_aa() -> None:
    resolved = palette.resolve()
    assert (resolved.text, resolved.background, resolved.minimum) == ("#000000", "#ffffff", 4.5)
    assert palette.DEFAULT == "AA"


def test_the_colours_that_failed_aa_are_corrected() -> None:
    """What the app drew before: light greys for deprecated, unnamed and
    context-only rows (2.3 to 2.9:1), the breadcrumb's #888888 (3.5:1)."""
    resolved = palette.resolve("AA")
    for role in ("deprecated", "unnamed", "context-only", "builtin", "muted"):
        assert palette.meets(resolved.foregrounds[role], "#ffffff", 4.5), role


def test_colours_that_already_pass_are_left_alone() -> None:
    """A colour is darkened only as far as it must be: at AA the red of a
    finding is the red it always was."""
    resolved = palette.resolve("AA")
    assert resolved.finding == palette.FOREGROUNDS["finding"]
    assert resolved.note == palette.FOREGROUNDS["note"]
    assert resolved.tints == palette.TINTS


def test_raising_the_level_never_lightens_a_foreground() -> None:
    previous = palette.resolve("AA")
    for level in LEVELS[1:]:
        if palette.parse(level) < previous.minimum:
            continue
        current = palette.resolve(level)
        for name, colour in current.foregrounds.items():
            assert palette.luminance(colour) <= palette.luminance(previous.foregrounds[name]) + 1e-12, (level, name)
        previous = current


def test_max_is_pure_black_and_white() -> None:
    resolved = palette.resolve("Max")
    colours = {resolved.text, resolved.background, *resolved.foregrounds.values(), *resolved.tints.values()}
    colours |= {c for s in resolved.selections.values() for c in (s.background, s.foreground)}
    assert colours == {"#000000", "#ffffff"}


def test_a_selection_that_cannot_be_tinted_is_inverted() -> None:
    resolved = palette.resolve("Max")
    assert all(s.inverted for s in resolved.selections.values())
    assert resolved.selections["active"] == palette.Selection("#000000", "#ffffff", True)
    assert not any(s.inverted for s in palette.resolve("AAA").selections.values())


def test_a_state_that_loses_its_colour_gets_another_cue() -> None:
    """At Max every row state would be plain black text and every relationship
    a plain white row; the states turn italic and the relationships bold."""
    assert palette.resolve("AA").cues == {}
    cues = palette.resolve("Max").cues
    assert {cues[t] for t in palette.STATES} == {"italic"}
    assert {cues[t] for t in palette.RELATIONS} == {"bold"}


@pytest.mark.parametrize(
    ("text", "ratio"),
    [("AA", 4.5), ("aaa", 7.0), (" max ", 21.0), ("10", 10.0), ("10:1", 10.0), (12.5, 12.5), (21, 21.0)],
)
def test_a_level_is_a_preset_or_a_ratio(text, ratio) -> None:
    assert palette.parse(text) == ratio


@pytest.mark.parametrize("text", ["", "A", "4.4", "22", "nan", "inf", None, True, [7]])
def test_anything_else_is_not_a_level(text) -> None:
    assert palette.parse(text) is None


def test_a_level_has_one_spelling() -> None:
    assert [palette.name_of(x) for x in ("aa", 7, "21:1", "10.0", "junk")] == ["AA", "AAA", "Max", "10", "AA"]
    assert palette.describe("AAA") == "AAA (7:1)"
    assert palette.describe(10) == "Custom (10:1)"


def test_no_colour_is_written_anywhere_but_the_palette() -> None:
    """The guarantee holds only for colours the palette knows about. A literal
    in a widget module is a pair nothing checks — which is how five colours
    below AA were found."""
    literal = re.compile(r"""["']#[0-9a-fA-F]{3,6}["']""")
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(SOURCE.glob("*.py"))
        if path.name != "palette.py"
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if literal.search(line)
    ]
    assert offenders == []
