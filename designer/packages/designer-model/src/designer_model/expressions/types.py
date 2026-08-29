"""The type universe.

Wider than the eight BaseTypes, in three directions the checker needs:

`duration` is a real intermediate value — `datetime - datetime` produces one —
but never the type of a slot, a Property, or a top-level result.

`unknown` absorbs. Any operation involving it yields it and reports nothing,
which is what keeps an incomplete item quiet (spec §3.1). It never *satisfies* a
requirement, only suppresses a complaint.

Untyped numeric literals take the type of their context, so `price <= 1.5` on a
decimal price is not a real/decimal error.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_TYPES = ("integer", "real", "decimal", "boolean", "string", "datetime", "date", "time")
NUMERIC = frozenset({"integer", "real", "decimal"})
TEMPORAL = frozenset({"datetime", "date", "time"})
ORDERED = NUMERIC | {"string", "date", "time", "datetime", "duration"}
EQUATABLE = ORDERED | {"boolean"}


class ExprType:
    """Base class. Instances are frozen and hashable."""


@dataclass(frozen=True, slots=True)
class Scalar(ExprType):
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class ListOf(ExprType):
    element: ExprType

    def __str__(self) -> str:
        return f"list[{self.element}]"


@dataclass(frozen=True, slots=True)
class Var(ExprType):
    """An unresolved type, standing for whatever the context forces.

    A `constraint` narrows what it may become. `current()` returns one limited
    to datetime and date, which is how `value < current()` is polymorphic over
    those two and a type error on anything else.
    """

    name: str
    constraint: frozenset[str] | None = None

    def __str__(self) -> str:
        return f"?{self.name}"


@dataclass(frozen=True, slots=True)
class Unknown(ExprType):
    """Not yet knowable. Absorbs, and reports nothing."""

    def __str__(self) -> str:
        return "unknown"


@dataclass(frozen=True, slots=True)
class UntypedNumber(ExprType):
    """A numeric literal before its context fixes it.

    `fractional` decides what it may become: an integer-shaped literal fits
    integer, real or decimal; a fraction-shaped one fits real or decimal only.
    Unconstrained, a fraction settles on decimal rather than real, because the
    source text is exact and reading it as binary floating point loses what the
    author wrote.
    """

    fractional: bool

    def __str__(self) -> str:
        return "number"


UNKNOWN = Unknown()
INTEGER = Scalar("integer")
REAL = Scalar("real")
DECIMAL = Scalar("decimal")
BOOLEAN = Scalar("boolean")
STRING = Scalar("string")
DATETIME = Scalar("datetime")
DATE = Scalar("date")
TIME = Scalar("time")
DURATION = Scalar("duration")

ALL_TYPES = (*(Scalar(n) for n in BASE_TYPES), DURATION)


def is_unknown(t: ExprType) -> bool:
    return isinstance(t, Unknown)


def is_numeric(t: ExprType) -> bool:
    return isinstance(t, UntypedNumber) or (isinstance(t, Scalar) and t.name in NUMERIC)


def settle(t: ExprType) -> ExprType:
    """Fix an untyped literal that nothing constrained."""
    if isinstance(t, UntypedNumber):
        return DECIMAL if t.fractional else INTEGER
    return t


def accepts_untyped(target: ExprType, literal: UntypedNumber) -> bool:
    if not isinstance(target, Scalar) or target.name not in NUMERIC:
        return False
    if literal.fractional and target.name == "integer":
        return False
    return True
