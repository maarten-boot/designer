"""Every colour the application draws, and the contrast each must reach.

Black text on white is the default. Every foreground is checked against every
background it can be drawn on, and darkened until the pair reaches the chosen
minimum contrast ratio (WCAG 2 relative luminance); every tinted background is
lightened until plain text on it does. So the colours written below are
*intent* — "a quiet grey", "a pale blue" — and `resolve` turns them into the
colours actually used.

Three presets and a custom ratio:

    AA    4.5:1   WCAG level AA for body text, the default
    AAA   7:1     WCAG level AAA
    Max   21:1    pure black on pure white, nothing else

At high ratios the greys and tints converge on black and white, and a state
carried only by colour would vanish. Where that happens `Palette.cues` says so,
and the widget layer marks the row in another way (italic for a state, bold for
a relationship). A selection that can no longer be tinted is shown inverted.

tkinter-free, so all of it is tested without a display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

PRESETS: dict[str, float] = {"AA": 4.5, "AAA": 7.0, "Max": 21.0}
DEFAULT = "AA"
LOWEST, HIGHEST = 4.5, 21.0
"""A custom ratio below AA is not offered: AA is the floor, not a choice."""

# --- intent -----------------------------------------------------------------

TEXT = "#000000"
BACKGROUND = "#ffffff"

FOREGROUNDS: dict[str, str] = {
    "finding": "#a01b0b",  # an error, in the form and the findings window
    "attention": "#a35a00",  # true and worth noticing, but not a fault
    "note": "#4f4f4f",  # secondary text: hints, notes, unfinished findings
    "readonly": "#3c3c3c",  # a value that is shown, not edited
    "passed": "#2d6a1f",  # the test bench: a value accepted
    "muted": "#767676",  # an absence: "(no context)"
    "disabled": "#8c8c8c",  # a control that cannot be used now
    # row states in the browser columns and the form's tables
    "abstract": "#555555",
    "builtin": "#666666",
    "deprecated": "#8c8c8c",
    "unnamed": "#7a7a7a",
    "incomplete": "#8a6d00",
    "context-only": "#8c8c8c",
}

TINTS: dict[str, str] = {
    # the relationship highlights: rows that the chosen item uses, references
    # or contains
    "uses": "#e8f0fe",
    "references": "#e6f4ea",
    "contains": "#fdf1e3",
    "tooltip": "#ffffe0",
}

SELECTIONS: dict[str, str] = {
    # several columns hold a selection at once, and only one is what the
    # editor shows: amber for that one, grey for the rest
    "active": "#ffcf5c",
    "idle": "#d8d8d8",
    # selected text in an entry or a text box
    "text": "#c3c3c3",
}

STATES = ("abstract", "builtin", "deprecated", "unnamed", "incomplete", "context-only")
RELATIONS = ("uses", "references", "contains")

DISTINCT = 1.5
"""Two colours closer than this ratio are taken to look the same — the point
at which a state needs a cue other than its colour."""


# --- contrast ---------------------------------------------------------------


def _rgb(colour: str) -> tuple[int, int, int]:
    text = colour.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a #rrggbb colour: {colour!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def luminance(colour: str) -> float:
    """WCAG 2 relative luminance, 0 for black and 1 for white."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    """The WCAG contrast ratio of two colours, from 1 to 21."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def meets(a: str, b: str, minimum: float) -> bool:
    # 1e-9: black on white is 21 in exact arithmetic and 20.999… in floats
    return ratio(a, b) >= minimum - 1e-9


def darken(colour: str, backgrounds: list[str], minimum: float) -> str:
    """The lightest shade of `colour`, towards black, that reaches `minimum`
    against every one of `backgrounds`. Hue is kept: the channels are scaled
    together, so a red stays a red until it has to become black."""
    if all(meets(colour, b, minimum) for b in backgrounds):
        return colour
    rgb = _rgb(colour)

    def shade(t: float) -> str:
        return _hex(tuple(math.floor(v * t) for v in rgb))  # type: ignore[arg-type]

    low, high = 0.0, 1.0  # shade(low) always passes: it is black
    for _ in range(40):
        middle = (low + high) / 2
        if all(meets(shade(middle), b, minimum) for b in backgrounds):
            low = middle
        else:
            high = middle
    return shade(low)


def lighten(colour: str, foreground: str, minimum: float) -> str:
    """The deepest tint of `colour`, towards white, on which `foreground`
    reaches `minimum`."""
    if meets(foreground, colour, minimum):
        return colour
    rgb = _rgb(colour)

    def tint(s: float) -> str:
        return _hex(tuple(math.ceil(v + (255 - v) * s) for v in rgb))  # type: ignore[arg-type]

    low, high = 0.0, 1.0  # tint(high) is white
    for _ in range(40):
        middle = (low + high) / 2
        if meets(foreground, tint(middle), minimum):
            high = middle
        else:
            low = middle
    return tint(high)


# --- levels -----------------------------------------------------------------


def parse(text: object) -> float | None:
    """A contrast level as a ratio: a preset name in any case, or a number
    from 4.5 to 21, optionally written `7:1`. None when it is neither."""
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        number = float(text)
    else:
        spelled = str(text).strip()
        for name, value in PRESETS.items():
            if spelled.lower() == name.lower():
                return value
        ratio, colon, one = spelled.partition(":")
        if colon and one.strip() != "1":
            return None
        spelled = ratio.strip()  # "7:1", "7 : 1" and "7" alike
        try:
            number = float(spelled)
        except ValueError:
            return None
    if not math.isfinite(number) or not LOWEST <= number <= HIGHEST:
        return None
    return number


def name_of(level: object) -> str:
    """The canonical spelling of a level: the preset's name, else the ratio."""
    value = parse(level)
    if value is None:
        return DEFAULT
    for name, preset in PRESETS.items():
        if value == preset:
            return name
    return f"{value:g}"


def describe(level: object) -> str:
    value = parse(level)
    if value is None:
        value = PRESETS[DEFAULT]
    name = name_of(level)
    return f"{name} ({value:g}:1)" if name in PRESETS else f"Custom ({value:g}:1)"


# --- the resolved palette ---------------------------------------------------


@dataclass(frozen=True)
class Selection:
    background: str
    foreground: str
    inverted: bool


@dataclass(frozen=True)
class Palette:
    minimum: float
    text: str
    background: str
    foregrounds: dict[str, str]
    tints: dict[str, str]
    selections: dict[str, Selection]
    cues: dict[str, str] = field(default_factory=dict)
    """Row tag → "italic" or "bold", for each state or relationship whose
    colour no longer tells it apart from plain text or a plain row."""

    def __getattr__(self, name: str) -> str:
        # palette.finding, palette.note, …: the foreground roles by name
        foregrounds = self.__dict__.get("foregrounds", {})
        if name in foregrounds:
            return str(foregrounds[name])
        raise AttributeError(name)

    def tag_styles(self) -> dict[str, dict[str, str]]:
        """Treeview tag options: the states as text colours, the relationships
        as row backgrounds."""
        styles = {tag: {"foreground": self.foregrounds[tag]} for tag in STATES}
        styles.update({tag: {"background": self.tints[tag]} for tag in RELATIONS})
        return styles

    def pairs(self) -> list[tuple[str, str, str]]:
        """Every foreground/background pair this palette can draw, named —
        what the contrast guarantee is about, and what the tests walk."""
        plain = [("background", self.background), *((f"tint {t}", c) for t, c in self.tints.items())]
        roles = [("text", self.text), *self.foregrounds.items()]
        out = [(f"{role} on {where}", fg, bg) for role, fg in roles for where, bg in plain]
        out += [(f"selected text on selection {n}", s.foreground, s.background) for n, s in self.selections.items()]
        return out


def resolve(level: object = DEFAULT) -> Palette:
    """The palette for a contrast level (a preset name or a ratio)."""
    minimum = parse(level)
    if minimum is None:
        minimum = PRESETS[DEFAULT]

    tints = {name: lighten(colour, TEXT, minimum) for name, colour in TINTS.items()}

    selections: dict[str, Selection] = {}
    for name, colour in SELECTIONS.items():
        shown = lighten(colour, TEXT, minimum)
        if ratio(shown, BACKGROUND) < 1.1:
            # it would have to be white to carry black text: invert instead
            selections[name] = Selection(TEXT, BACKGROUND, True)
        else:
            selections[name] = Selection(shown, TEXT, False)

    # a foreground is drawn on the plain background and on each tint. Not on
    # a selection: a selected row is drawn in the selection's own pair, which
    # wins over the row's tag colours (Tk 8.6.10 and later)
    grounds = [BACKGROUND, *tints.values()]
    foregrounds = {name: darken(colour, grounds, minimum) for name, colour in FOREGROUNDS.items()}

    cues: dict[str, str] = {}
    for tag in STATES:
        if ratio(foregrounds[tag], TEXT) < DISTINCT:
            cues[tag] = "italic"
    for tag in RELATIONS:
        if ratio(tints[tag], BACKGROUND) < 1.05:
            cues[tag] = "bold"

    return Palette(minimum, TEXT, BACKGROUND, foregrounds, tints, selections, cues)


_current = resolve(DEFAULT)


def current() -> Palette:
    """The palette in use. Widgets read it when they are built, so a change of
    level reaches a window the next time it is drawn; `theme.apply` redraws
    what is already open."""
    return _current


def use(level: object) -> Palette:
    global _current
    _current = resolve(level)
    return _current
