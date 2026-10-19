"""Literals.

Values that JSON cannot carry faithfully are stored as tagged strings
(spec §4.1), and `datetime` is timezone-aware UTC always (spec §4.2). The
envelope is a single-key object naming the BaseType:

    {"integer": 80}
    {"decimal": "0.00"}
    {"datetime": "2026-08-29T14:30:00Z"}
    {"list": {"string": ["low", "normal"]}}
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

BASE_TYPES = frozenset({"integer", "real", "decimal", "boolean", "string", "datetime", "date", "time"})


class LiteralError(ValueError):
    """A literal that cannot be represented, distinct from a malformed document."""


@dataclass(frozen=True, slots=True)
class ScalarLiteral:
    base_type: str
    value: Any

    def __post_init__(self) -> None:
        if self.base_type not in BASE_TYPES:
            raise LiteralError(f"unknown base type {self.base_type!r}")


@dataclass(frozen=True, slots=True)
class ListLiteral:
    element_type: str
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if self.element_type not in BASE_TYPES:
            raise LiteralError(f"unknown element type {self.element_type!r}")


Literal = ScalarLiteral | ListLiteral


def _decode_datetime(text: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        # spec §4.2: naive datetimes are rejected on entry and on load
        raise LiteralError(f"datetime {text!r} has no timezone; UTC is required")
    return parsed.astimezone(dt.UTC)


def _decode_time(text: str) -> dt.time:
    parsed = dt.time.fromisoformat(text)
    if parsed.tzinfo is not None:
        raise LiteralError(f"time {text!r} carries a zone; a time of day has none (spec §4.1)")
    return parsed


_DECODERS = {
    "integer": int,
    "real": float,
    "decimal": Decimal,
    "boolean": bool,
    "string": str,
    "datetime": _decode_datetime,
    "date": dt.date.fromisoformat,
    "time": _decode_time,
}


_JSON_KINDS: dict[str, tuple[type, ...]] = {
    "integer": (int,),
    "real": (int, float),
    "decimal": (str,),
    "boolean": (bool,),
    "string": (str,),
    "datetime": (str,),
    "date": (str,),
    "time": (str,),
}
"""What JSON may carry for each base type. A decimal is a string because JSON
numbers are binary floating point (§4.1) — `0.1` read as a number would arrive
as `0.1000000000000000055…`, which is the loss the tagged string exists to
prevent. Conversions are never applied on load: `1.9` is not an integer and
`"false"` is not a boolean, and saying so beats storing 1 and true."""

_CANONICAL = {
    "decimal": re.compile(r"-?\d+(\.\d+)?"),
    "date": re.compile(r"\d{4}-\d{2}-\d{2}"),
    # a zone is allowed by the shape so that `_decode_time` can say what is wrong with it
    "time": re.compile(r"\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?"),
    "datetime": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})"),
}
"""The one spelling the file uses for each, as `encode` writes it (spec §4.1)."""

_WRITTEN_AS = {
    "integer": "a whole number",
    "real": "a number",
    "decimal": 'a string, such as "0.10"',
    "boolean": "true or false",
    "string": "a string",
    "datetime": 'a string, such as "2026-08-29T14:30:00Z"',
    "date": 'a string, such as "2026-08-29"',
    "time": 'a string, such as "14:30:00"',
}


def _decode_scalar(base_type: str, raw: Any) -> Any:
    if base_type == "integer" and isinstance(raw, bool):
        raise LiteralError("boolean supplied where integer expected")
    allowed = _JSON_KINDS.get(base_type)
    if allowed is not None and (not isinstance(raw, allowed) or (base_type == "real" and isinstance(raw, bool))):
        raise LiteralError(f"{base_type} is written as {_WRITTEN_AS[base_type]}, not {raw!r}")
    shape = _CANONICAL.get(base_type)
    if shape is not None and not shape.fullmatch(raw):
        # `20260829` or `1430` would read, and be rewritten on save: the file
        # holds one spelling of each value, so anything else is refused
        raise LiteralError(f"{base_type} is written as {_WRITTEN_AS[base_type]}, not {raw!r}")
    try:
        value = _DECODERS[base_type](raw)
    except LiteralError:
        raise  # already says what is wrong
    except (ValueError, ArithmeticError) as error:  # decimal raises InvalidOperation
        raise LiteralError(f"{raw!r} is not a {base_type}") from error
    if base_type in {"decimal", "real"} and not math.isfinite(value):
        raise LiteralError(f"{raw!r} is not a finite {base_type}")
    return value


def _encode_scalar(base_type: str, value: Any) -> Any:
    if base_type in {"integer", "real", "boolean", "string"}:
        return value
    if base_type == "decimal":
        return str(value)
    if base_type == "datetime":
        return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def decode(raw: dict[str, Any]) -> Literal:
    if len(raw) != 1:
        raise LiteralError(f"a literal is one tagged key, got {sorted(raw)}")
    ((tag, body),) = raw.items()
    if tag == "list":
        if not isinstance(body, dict) or len(body) != 1:
            raise LiteralError("a list literal is one tagged key holding an array")
        ((element_type, values),) = body.items()
        if element_type not in BASE_TYPES:
            raise LiteralError(f"unknown element type {element_type!r}")
        if not isinstance(values, list):
            # a string is iterable, and `"abc"` would load as three letters
            raise LiteralError(f"a list literal holds an array, not {values!r}")
        return ListLiteral(element_type, tuple(_decode_scalar(element_type, v) for v in values))
    if tag not in BASE_TYPES:
        raise LiteralError(f"unknown literal tag {tag!r}")
    return ScalarLiteral(tag, _decode_scalar(tag, body))


def encode(literal: Literal) -> dict[str, Any]:
    if isinstance(literal, ListLiteral):
        return {"list": {literal.element_type: [_encode_scalar(literal.element_type, v) for v in literal.values]}}
    return {literal.base_type: _encode_scalar(literal.base_type, literal.value)}
