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


_DECODERS = {
    "integer": int,
    "real": float,
    "decimal": Decimal,
    "boolean": bool,
    "string": str,
    "datetime": _decode_datetime,
    "date": dt.date.fromisoformat,
    "time": dt.time.fromisoformat,
}


def _decode_scalar(base_type: str, raw: Any) -> Any:
    if base_type == "integer" and isinstance(raw, bool):
        raise LiteralError("boolean supplied where integer expected")
    return _DECODERS[base_type](raw)


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
        return ListLiteral(element_type, tuple(_decode_scalar(element_type, v) for v in values))
    if tag not in BASE_TYPES:
        raise LiteralError(f"unknown literal tag {tag!r}")
    return ScalarLiteral(tag, _decode_scalar(tag, body))


def encode(literal: Literal) -> dict[str, Any]:
    if isinstance(literal, ListLiteral):
        return {"list": {literal.element_type: [_encode_scalar(literal.element_type, v) for v in literal.values]}}
    return {literal.base_type: _encode_scalar(literal.base_type, literal.value)}
