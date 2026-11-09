"""Edit ▸ Preferences…, decided without a window.

The three numeric settings spec §15 names, each with the range it may take,
and the contrast level (spec §13.12). Reading
what was typed, saying what is wrong with it, and applying it to the running
application are all here and tested; the dialog in `dialogs.py` only shows the
fields and the complaint.
"""

from __future__ import annotations

from dataclasses import dataclass

from designer_model.commands import CommandStack

from . import palette
from .state import Settings


@dataclass(frozen=True, slots=True)
class Preference:
    key: str
    label: str
    minimum: int
    maximum: int
    hint: str


PREFERENCES = (
    Preference("undo_limit", "Undo steps kept", 1, 10_000, "a delete can hold a whole context, so this bounds memory"),
    Preference(
        "autosave_delay_ms", "Autosave after (ms)", 50, 60_000, "how long the model is quiet before it is saved"
    ),
    Preference("recent_files_limit", "Recent files listed", 1, 50, "under File ▸ Open Recent"),
)

CONTRAST = "contrast"
CONTRAST_LABEL = "Minimum contrast"
CONTRAST_CHOICES = tuple(palette.PRESETS)
CONTRAST_HINT = (
    f"AA {palette.PRESETS['AA']:g}:1, AAA {palette.PRESETS['AAA']:g}:1, Max 21:1 (black and white), "
    f"or a ratio from {palette.LOWEST:g} to {palette.HIGHEST:g}"
)

Value = int | str


def current(settings: Settings) -> dict[str, str]:
    """What the dialog opens with."""
    values = {p.key: str(getattr(settings, p.key)) for p in PREFERENCES}
    values[CONTRAST] = palette.name_of(settings.contrast)
    return values


def check(values: dict[str, str]) -> tuple[dict[str, Value], str]:
    """The values as numbers, or the first thing wrong with them.

    One complaint at a time, naming the field and its range: a list of every
    fault in a three-field dialog says less than the one that matters.
    """
    out: dict[str, Value] = {}
    for p in PREFERENCES:
        text = values.get(p.key, "").strip().replace("_", "")
        try:
            number = int(text)
        except ValueError:
            return {}, f"{p.label} must be a whole number"
        if not p.minimum <= number <= p.maximum:
            return {}, f"{p.label} must be between {p.minimum:,} and {p.maximum:,}"
        out[p.key] = number
    if CONTRAST in values:
        if palette.parse(values[CONTRAST]) is None:
            span = f"{palette.LOWEST:g} to {palette.HIGHEST:g}"
            return {}, f"{CONTRAST_LABEL} must be AA, AAA, Max or a ratio from {span}"
        out[CONTRAST] = palette.name_of(values[CONTRAST])
    return out, ""


def apply(values: dict[str, Value], settings: Settings, stack: CommandStack) -> None:
    """Take effect now, not at the next start: the undo stack is trimmed, the
    recent list is cut, and the next autosave waits the new delay."""
    for key, number in values.items():
        setattr(settings, key, number)
    stack.set_limit(settings.undo_limit)
    del settings.recent_files[settings.recent_files_limit :]
