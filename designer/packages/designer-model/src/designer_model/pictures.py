"""Presenting a value, and reading one back.

A picture says how a value is written down for a person and how a person's
writing is read back. It never decides whether a value is *allowed* — that is a
Validator's job, and it happens after parsing and before presenting.

The law this module exists to keep:

    parse(present(v)) == v

for every value the type admits. `check_round_trip` is that law as a function.
Most picture mistakes are failures of it — `#,##0.00` on a type allowing four
decimal places rounds on the way out and cannot recover the original on the way
back — and finding them when the picture is written is much cheaper than
finding them in a form six months later.

Domain, not interface: the export carries pictures, so a generator needs them
without needing a window.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

NUMERIC = {"integer", "decimal", "real"}
TEMPORAL = {"date", "time", "datetime"}

# yyyy before yy, and MM before M, so the longer token wins the match
TEMPORAL_TOKENS = ("yyyy", "yy", "MM", "dd", "HH", "mm", "ss", "SSS", "ZZ")

TEMPORAL_FIELDS = {
    "date": {"yyyy", "yy", "MM", "dd"},
    "time": {"HH", "mm", "ss", "SSS"},
    "datetime": {"yyyy", "yy", "MM", "dd", "HH", "mm", "ss", "SSS", "ZZ"},
}


class PictureError(ValueError):
    """A picture that is not valid for its base type."""


class PresentError(ValueError):
    """A value that cannot be written in this picture."""


class ParseError(ValueError):
    """Text that cannot be read back. Not a validation failure: there is no
    value to validate, which is a different thing to tell somebody."""


# --- numeric -----------------------------------------------------------------


ALLOWED_SEPARATORS = {".", ",", "'", " ", "\u00a0", ""}
"""Point, comma, apostrophe (Swiss), space and non-breaking space. Empty is
allowed for grouping only, to write a group size that shows no separator."""


@dataclass(frozen=True, slots=True)
class Numeric:
    base_type: str
    minimum_digits: int
    minimum_decimals: int
    maximum_decimals: int
    grouping: int
    always_sign: bool
    percent: bool
    negative: str | None
    text: str
    decimal_point: str = "."
    group_mark: str = ","
    """What the separators are *written as*.

    The picture itself is always canonical — `.` decimal, `,` grouping — and
    these two say how it is rendered. Writing them literally in the picture was
    considered and rejected: with only one separator present, `#,##0` and
    `0,00` become indistinguishable, and the rule needed to tell them apart
    ("the last separator is the decimal one") gets `#,##0` wrong.

    Keeping the picture canonical also means one grammar to check and one set
    of tests, and it lets a single picture serve every region: the structure
    (grouped by three, two decimals) is the same everywhere, and only these two
    characters differ.
    """


def _compile_numeric(base_type: str, text: str, decimal_point: str = ".", group_mark: str = ",") -> Numeric:
    if decimal_point not in ALLOWED_SEPARATORS or not decimal_point:
        raise PictureError(f"{decimal_point!r} is not a decimal separator")
    if group_mark not in ALLOWED_SEPARATORS:
        raise PictureError(f"{group_mark!r} is not a grouping separator")
    if decimal_point == group_mark:
        raise PictureError("the decimal and grouping separators must differ")
    positive, _, negative = text.partition(";")
    percent = positive.endswith("%")
    body = positive.removesuffix("%")
    if percent and base_type == "integer":
        # stored 1 shows as 100%, and 7.5% is unreachable: the smallest step a
        # percentage can express on an integer is 100%, so it is always a mistake
        raise PictureError("a percentage picture needs a decimal or real, not an integer")

    always_sign = body.startswith("+")
    body = body.lstrip("+-")

    whole, point, fraction = body.partition(".")
    if not point and "." in fraction:
        raise PictureError("more than one decimal separator")
    if base_type == "integer" and fraction:
        raise PictureError("an integer picture cannot have decimal places")
    if set(whole) - set("0#,") or set(fraction) - set("0#"):
        raise PictureError(f"{text!r} is not a numeric picture")
    if not whole and not fraction:
        raise PictureError("a numeric picture needs at least one digit position")
    if "#" in whole.rstrip("0") and "0" in whole and whole.rindex("0") < whole.rindex("#"):
        raise PictureError("optional positions must come before required ones")
    if "0" in fraction.lstrip("0") and "#" in fraction and fraction.index("#") < fraction.rindex("0"):
        raise PictureError("required decimals must come before optional ones")

    grouping = 0
    if "," in whole:
        grouping = len(whole) - whole.rindex(",") - 1
        if grouping == 0:
            raise PictureError("a grouping separator needs digits after it")

    return Numeric(
        base_type=base_type,
        decimal_point=decimal_point,
        group_mark=group_mark,
        minimum_digits=whole.count("0"),
        minimum_decimals=fraction.count("0"),
        maximum_decimals=len(fraction),
        grouping=grouping,
        always_sign=always_sign,
        percent=percent,
        negative=negative or None,
        text=text,
    )


def _group(digits: str, size: int) -> str:
    if not size:
        return digits
    out = []
    while len(digits) > size:
        out.append(digits[-size:])
        digits = digits[:-size]
    out.append(digits)
    return ",".join(reversed(out))


def _present_numeric(picture: Numeric, value) -> str:
    number = Decimal(str(value))
    if picture.percent:
        number *= 100
    negative = number < 0
    number = abs(number)

    if picture.maximum_decimals or picture.base_type != "integer":
        number = number.quantize(Decimal(1).scaleb(-picture.maximum_decimals))
    whole, _, fraction = f"{number:f}".partition(".")

    whole = whole.rjust(picture.minimum_digits, "0")
    shown = _group(whole, picture.grouping)
    fraction = fraction.rstrip("0")
    while len(fraction) < picture.minimum_decimals:
        fraction += "0"
    shown = shown.replace(",", picture.group_mark)
    if fraction:
        shown = f"{shown}{picture.decimal_point}{fraction}"
    if picture.percent:
        shown += "%"

    if negative:
        if picture.negative:
            return picture.negative.replace("#", "").replace("0", "").replace(",", "").join(()) or _apply_negative(
                picture, shown
            )
        return f"-{shown}"
    return f"+{shown}" if picture.always_sign else shown


def _apply_negative(picture: Numeric, shown: str) -> str:
    """The negative picture with the digits of the presented value put back.

    `(#,##0.00)` means "the same number, in brackets" — the digit positions in
    it are the same positions, not a second format to work out.
    """
    template = picture.negative or ""
    body = re.sub(r"[0#,.%+-]+", "\x00", template)
    return body.replace("\x00", shown, 1)


def _parse_numeric(picture: Numeric, text: str, lenient: bool):
    cleaned = text.strip() if lenient else text
    negative = False
    if picture.negative and cleaned.startswith("(") and cleaned.endswith(")"):
        negative, cleaned = True, cleaned[1:-1]
    if cleaned.startswith("-"):
        negative, cleaned = True, cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]
    cleaned = cleaned.removesuffix("%") if picture.percent else cleaned
    grouped = picture.group_mark and picture.group_mark in cleaned
    if not lenient and picture.grouping and not grouped:
        whole = cleaned.partition(picture.decimal_point)[0]
        if len(whole) > picture.grouping:
            raise ParseError(f"{text!r} is missing its grouping separators")
    if picture.group_mark:
        cleaned = cleaned.replace(picture.group_mark, "")
    # to canonical form, so Decimal can read it whatever the region writes
    cleaned = cleaned.replace(picture.decimal_point, ".") if picture.decimal_point != "." else cleaned
    if not cleaned:
        raise ParseError("no digits")
    try:
        number = Decimal(cleaned)
    except InvalidOperation as error:
        raise ParseError(f"{text!r} is not a number") from error
    if picture.percent:
        number /= 100
    if negative:
        number = -number
    if picture.base_type == "integer":
        if number != number.to_integral_value():
            raise ParseError(f"{text!r} is not a whole number")
        return int(number)
    if picture.base_type == "real":
        return float(number)
    return number


# --- string ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Text:
    positions: int
    align: str
    case: str
    text: str


def _compile_string(text: str) -> Text:
    match = re.fullmatch(r"X\((\d+)\)([<>^]?)([UL]?)", text)
    if not match:
        raise PictureError(f"{text!r} is not a string picture; expected X(n) with < > ^ U or L")
    return Text(int(match.group(1)), match.group(2) or "<", match.group(3), text)


def _present_string(picture: Text, value: str) -> str:
    shown = value.upper() if picture.case == "U" else value.lower() if picture.case == "L" else value
    # never truncated: the positions are a hint about width, and an application
    # may scroll or wrap. A length that is meant to be a limit is a rule.
    if picture.align == ">":
        return shown.rjust(picture.positions)
    if picture.align == "^":
        return shown.center(picture.positions)
    return shown.ljust(picture.positions)


def _parse_string(picture: Text, text: str, lenient: bool) -> str:
    return text.strip() if lenient or picture.positions else text


# --- temporal ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Temporal:
    base_type: str
    parts: tuple[str, ...]
    text: str


def _split_temporal(text: str) -> tuple[str, ...]:
    parts: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "'":
            end = text.find("'", index + 1)
            if end == -1:
                raise PictureError("unclosed quoted text")
            parts.append(text[index : end + 1])
            index = end + 1
            continue
        for token in TEMPORAL_TOKENS:
            if text.startswith(token, index):
                parts.append(token)
                index += len(token)
                break
        else:
            parts.append(text[index])
            index += 1
    return tuple(parts)


def _compile_temporal(base_type: str, text: str) -> Temporal:
    parts = _split_temporal(text)
    allowed = TEMPORAL_FIELDS[base_type]
    used = [p for p in parts if p in TEMPORAL_TOKENS]
    if not used:
        raise PictureError("a date or time picture needs at least one field")
    for token in used:
        if token not in allowed:
            raise PictureError(f"{token} is not a field of {base_type}")
    if len(set(used)) != len(used):
        raise PictureError("a field appears twice")
    return Temporal(base_type, parts, text)


def _present_temporal(picture: Temporal, value) -> str:
    out = []
    for part in picture.parts:
        if part.startswith("'"):
            out.append(part[1:-1])
        elif part == "yyyy":
            out.append(f"{value.year:04d}")
        elif part == "yy":
            out.append(f"{value.year % 100:02d}")
        elif part == "MM":
            out.append(f"{value.month:02d}")
        elif part == "dd":
            out.append(f"{value.day:02d}")
        elif part == "HH":
            out.append(f"{value.hour:02d}")
        elif part == "mm":
            out.append(f"{value.minute:02d}")
        elif part == "ss":
            out.append(f"{value.second:02d}")
        elif part == "SSS":
            out.append(f"{value.microsecond // 1000:03d}")
        elif part == "ZZ":
            offset = value.utcoffset() or dt.timedelta(0)
            total = int(offset.total_seconds())
            sign = "+" if total >= 0 else "-"
            out.append(f"{sign}{abs(total) // 3600:02d}:{abs(total) % 3600 // 60:02d}")
        else:
            out.append(part)
    return "".join(out)


_WIDTHS = {"yyyy": 4, "yy": 2, "MM": 2, "dd": 2, "HH": 2, "mm": 2, "ss": 2, "SSS": 3, "ZZ": 6}


def _parse_temporal(picture: Temporal, text: str, lenient: bool):
    working = text.strip() if lenient else text
    found: dict[str, int] = {}
    offset = dt.timedelta(0)
    for part in picture.parts:
        if part in TEMPORAL_TOKENS:
            width = _WIDTHS[part]
            chunk, working = working[:width], working[width:]
            if part == "ZZ":
                if len(chunk) != 6 or chunk[3] != ":":
                    raise ParseError(f"{text!r}: expected an offset like +01:00")
                minutes = int(chunk[1:3]) * 60 + int(chunk[4:6])
                offset = dt.timedelta(minutes=minutes * (-1 if chunk[0] == "-" else 1))
                continue
            if not chunk.isdigit() or len(chunk) != width:
                raise ParseError(f"{text!r}: expected {width} digits for {part}")
            found[part] = int(chunk)
        else:
            literal = part[1:-1] if part.startswith("'") else part
            if not working.startswith(literal):
                raise ParseError(f"{text!r}: expected {literal!r}")
            working = working[len(literal) :]
    if working:
        raise ParseError(f"{text!r} has {working!r} left over")

    year = found.get("yyyy", 2000 + found["yy"] if "yy" in found else 1900)
    try:
        if picture.base_type == "date":
            return dt.date(year, found.get("MM", 1), found.get("dd", 1))
        if picture.base_type == "time":
            return dt.time(
                found.get("HH", 0),
                found.get("mm", 0),
                found.get("ss", 0),
                found.get("SSS", 0) * 1000,
            )
        moment = dt.datetime(
            year,
            found.get("MM", 1),
            found.get("dd", 1),
            found.get("HH", 0),
            found.get("mm", 0),
            found.get("ss", 0),
            found.get("SSS", 0) * 1000,
            tzinfo=dt.UTC,
        )
        # a picture with no ZZ presents and reads UTC; the model carries no
        # local zone, and inventing one here would put a rule about time in
        # the presentation layer
        return moment - offset if "ZZ" in picture.parts else moment
    except ValueError as error:
        raise ParseError(f"{text!r}: {error}") from error


# --- boolean -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Boolean:
    yes: str
    no: str
    text: str


def _compile_boolean(text: str) -> Boolean:
    yes, separator, no = text.partition(";")
    if not separator or not yes or not no:
        raise PictureError("a boolean picture is two labels separated by ';', such as Yes;No")
    if yes == no:
        raise PictureError("the two labels must differ, or the value cannot be read back")
    return Boolean(yes, no, text)


def _parse_boolean(picture: Boolean, text: str, lenient: bool) -> bool:
    candidate = text.strip() if lenient else text
    if lenient:
        candidate = candidate.casefold()
        if candidate == picture.yes.casefold():
            return True
        if candidate == picture.no.casefold():
            return False
    elif candidate in (picture.yes, picture.no):
        return candidate == picture.yes
    raise ParseError(f"{text!r} is neither {picture.yes!r} nor {picture.no!r}")


# --- the public face ---------------------------------------------------------

Compiled = Numeric | Text | Temporal | Boolean


def compile_picture(base_type: str, text: str, decimal_point: str = ".", group_mark: str = ",") -> Compiled:
    """Check a picture against its base type, and prepare it for use.

    The separators apply to numbers only. Dates need nothing equivalent: a
    region that writes `30/08/2026` writes a different picture, because the
    separator there is literal text rather than a role.
    """
    if not text.strip():
        raise PictureError("no picture yet")
    if base_type in NUMERIC:
        return _compile_numeric(base_type, text, decimal_point, group_mark)
    if base_type in TEMPORAL:
        return _compile_temporal(base_type, text)
    if base_type == "string":
        return _compile_string(text)
    if base_type == "boolean":
        return _compile_boolean(text)
    raise PictureError(f"no pictures are defined for {base_type}")


def present(picture: Compiled, value) -> str:
    if value is None:
        return ""
    if isinstance(picture, Numeric):
        return _present_numeric(picture, value)
    if isinstance(picture, Text):
        return _present_string(picture, str(value))
    if isinstance(picture, Temporal):
        return _present_temporal(picture, value)
    return picture.yes if value else picture.no


def parse(picture: Compiled, text: str, lenient: bool = True):
    if isinstance(picture, Numeric):
        return _parse_numeric(picture, text, lenient)
    if isinstance(picture, Text):
        return _parse_string(picture, text, lenient)
    if isinstance(picture, Temporal):
        return _parse_temporal(picture, text, lenient)
    return _parse_boolean(picture, text, lenient)


@dataclass
class RoundTrip:
    """What a picture does to a set of sample values."""

    failures: list[tuple[object, str, str]] = field(default_factory=list)

    @property
    def holds(self) -> bool:
        return not self.failures

    def why(self) -> str:
        value, shown, back = self.failures[0]
        return f"{value!r} presents as {shown!r} and reads back as {back}"


def check_round_trip(picture: Compiled, samples) -> RoundTrip:
    """`parse(present(v)) == v` for each sample.

    This is where most picture mistakes live: a format that rounds on the way
    out cannot recover the original on the way back, and nothing about the
    picture looks wrong until somebody's total changes by a penny.
    """
    result = RoundTrip()
    for value in samples:
        shown = present(picture, value)
        try:
            back = parse(picture, shown)
        except ParseError as error:
            result.failures.append((value, shown, f"unreadable: {error}"))
            continue
        if back != value:
            result.failures.append((value, shown, repr(back)))
    return result
