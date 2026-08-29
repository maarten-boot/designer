"""The signature tables.

Pure data, walked by the checker. Nothing here imports the checker, so the
tables can be tested, rendered and diffed on their own — which is what makes the
committed operator matrix (tools/build_matrix.py) meaningful.

Numeric pairs are enumerated rather than derived from a promotion lattice. There
are nine, they fit on one screen, and an explicit row is easier to test and to
argue about than a rule that computes the same answer.

A rejection is a row too. "There is a rule and it says no" deserves a better
message than "no rule exists", and the two are different facts.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import (
    BOOLEAN,
    DATE,
    DATETIME,
    DECIMAL,
    DURATION,
    INTEGER,
    NUMERIC,
    ORDERED,
    REAL,
    STRING,
    ExprType,
    ListOf,
    Scalar,
    Var,
)


@dataclass(frozen=True, slots=True)
class Reject:
    """A deliberate refusal, with the code that explains it."""

    code: str
    hint: str = ""


# --- arithmetic -------------------------------------------------------------

MIXED_EXACTNESS = Reject(
    "EXP201",
    "real and decimal cannot be combined; binary floating point would destroy "
    "the decimal's exactness. Convert explicitly with float(...) if that is the intent.",
)

# +, -, * over the nine numeric pairs
ARITHMETIC: dict[tuple[str, str], Scalar | Reject] = {
    ("integer", "integer"): INTEGER,
    ("integer", "real"): REAL,
    ("real", "integer"): REAL,
    ("real", "real"): REAL,
    ("integer", "decimal"): DECIMAL,
    ("decimal", "integer"): DECIMAL,
    ("decimal", "decimal"): DECIMAL,
    ("real", "decimal"): MIXED_EXACTNESS,
    ("decimal", "real"): MIXED_EXACTNESS,
}

# / differs from the rest in exactly one cell: integer / integer widens
DIVISION: dict[tuple[str, str], Scalar | Reject] = {**ARITHMETIC, ("integer", "integer"): REAL}

REMAINDER: dict[tuple[str, str], Scalar | Reject] = {
    ("integer", "integer"): INTEGER,
    ("decimal", "decimal"): DECIMAL,
}

STRING_CONCAT = {("string", "string"): STRING}

NO_TIME_ARITHMETIC = Reject(
    "EXP203",
    "time supports comparison only; wrapping at midnight would quietly turn "
    "23:00 + 2h into 01:00. Model a duration instead.",
)

NAMED_UNITS = Reject(
    "EXP205",
    "a bare number has no units here; use days(n), hours(n) and so on.",
)

TEMPORAL: dict[tuple[str, str, str], Scalar | Reject] = {
    ("-", "datetime", "datetime"): DURATION,
    ("-", "date", "date"): DURATION,
    ("-", "time", "time"): NO_TIME_ARITHMETIC,
    ("+", "datetime", "duration"): DATETIME,
    ("-", "datetime", "duration"): DATETIME,
    ("+", "date", "duration"): DATE,
    ("-", "date", "duration"): DATE,
    ("+", "duration", "duration"): DURATION,
    ("-", "duration", "duration"): DURATION,
    ("*", "duration", "integer"): DURATION,
    ("*", "duration", "real"): DURATION,
    ("*", "integer", "duration"): DURATION,
    ("*", "real", "duration"): DURATION,
    ("/", "duration", "integer"): DURATION,
    ("/", "duration", "real"): DURATION,
    ("/", "duration", "duration"): REAL,
    # named refusals, so the message can point at the fix
    ("+", "date", "integer"): NAMED_UNITS,
    ("-", "date", "integer"): NAMED_UNITS,
    ("+", "datetime", "integer"): NAMED_UNITS,
    ("-", "datetime", "integer"): NAMED_UNITS,
    ("-", "date", "datetime"): Reject(
        "EXP204", "a date has no time or zone; convert explicitly before comparing or subtracting."
    ),
    ("-", "datetime", "date"): Reject(
        "EXP204", "a date has no time or zone; convert explicitly before comparing or subtracting."
    ),
}

COMPARISON_REJECTS: dict[tuple[str, str], Reject] = {
    ("real", "decimal"): MIXED_EXACTNESS,
    ("decimal", "real"): MIXED_EXACTNESS,
    ("date", "datetime"): Reject("EXP204", "a date has no time or zone; convert explicitly before comparing."),
    ("datetime", "date"): Reject("EXP204", "a date has no time or zone; convert explicitly before comparing."),
}

NOT_ORDERED = Reject("EXP206", "booleans are not ordered; use == instead.")
NO_TRUTHINESS = Reject("EXP207", "no implicit truth value here; compare explicitly.")
NO_SUBSTRING_IN = Reject("EXP208", "use contains(haystack, needle) rather than `in` on strings.")
NO_IDENTITY = Reject("EXP209", "`is` is not supported; use ==.")
NO_FLOOR_DIVISION = Reject("EXP210", "`//` is not supported; there is one division operator.")
NO_REPETITION = Reject("EXP211", "strings cannot be multiplied.")


# --- functions --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Signature:
    name: str
    params: tuple[ExprType, ...]
    result: ExprType
    deterministic: bool = True
    variadic: bool = False
    literal_params: tuple[int, ...] = ()
    constraint: frozenset[str] | None = None


def _s(name, params, result, **kw) -> Signature:
    return Signature(name, tuple(params), result, **kw)


_ORDERED_VAR = Var("T")

FUNCTIONS: dict[str, tuple[Signature, ...]] = {
    # string — free functions, because attribute access is banned outright and
    # keeping that ban absolute is worth more than method syntax
    "len": (_s("len", [STRING], INTEGER),),
    "lower": (_s("lower", [STRING], STRING),),
    "upper": (_s("upper", [STRING], STRING),),
    "strip": (_s("strip", [STRING], STRING),),
    "starts_with": (_s("starts_with", [STRING, STRING], BOOLEAN),),
    "ends_with": (_s("ends_with", [STRING, STRING], BOOLEAN),),
    "contains": (_s("contains", [STRING, STRING], BOOLEAN),),
    # the pattern must be a literal, so it compiles at authoring time and caches
    "regex_full_match": (_s("regex_full_match", [STRING, STRING], BOOLEAN, literal_params=(1,)),),
    # numeric
    "abs": (
        _s("abs", [INTEGER], INTEGER),
        _s("abs", [REAL], REAL),
        _s("abs", [DECIMAL], DECIMAL),
        _s("abs", [DURATION], DURATION),
    ),
    "min": (_s("min", [_ORDERED_VAR, _ORDERED_VAR], _ORDERED_VAR, variadic=True, constraint=ORDERED),),
    "max": (_s("max", [_ORDERED_VAR, _ORDERED_VAR], _ORDERED_VAR, variadic=True, constraint=ORDERED),),
    "round": (
        _s("round", [REAL], INTEGER),
        _s("round", [REAL, INTEGER], REAL),
        _s("round", [DECIMAL, INTEGER], DECIMAL),
    ),
    "is_finite": (_s("is_finite", [REAL], BOOLEAN),),
    "precision": (_s("precision", [DECIMAL], INTEGER),),
    "scale": (_s("scale", [DECIMAL], INTEGER),),
    # conversion
    "int": (_s("int", [REAL], INTEGER), _s("int", [DECIMAL], INTEGER), _s("int", [STRING], INTEGER)),
    "float": (
        _s("float", [INTEGER], REAL),
        _s("float", [DECIMAL], REAL),
        _s("float", [STRING], REAL),
    ),
    "str": (_s("str", [Var("A")], STRING),),
    "decimal": (_s("decimal", [STRING], DECIMAL), _s("decimal", [INTEGER], DECIMAL)),
    # clock — the three non-deterministic functions
    "now": (_s("now", [], Scalar("datetime"), deterministic=False),),
    "today": (_s("today", [], Scalar("date"), deterministic=False),),
    "current": (_s("current", [], Var("C"), deterministic=False, constraint=frozenset({"datetime", "date"})),),
    # duration constructors: without these, `duration` has no literal form and
    # `(end - start) < days(30)` cannot be written at all
    "seconds": (_s("seconds", [Var("N")], DURATION, constraint=NUMERIC),),
    "minutes": (_s("minutes", [Var("N")], DURATION, constraint=NUMERIC),),
    "hours": (_s("hours", [Var("N")], DURATION, constraint=NUMERIC),),
    "days": (_s("days", [Var("N")], DURATION, constraint=NUMERIC),),
    "weeks": (_s("weeks", [Var("N")], DURATION, constraint=NUMERIC),),
    "total_seconds": (_s("total_seconds", [DURATION], REAL),),
    "total_days": (_s("total_days", [DURATION], REAL),),
}

REJECTED_FUNCTIONS: dict[str, Reject] = {
    "Decimal": Reject("EXP303", "use lowercase decimal(...)"),
    "datetime": Reject("EXP303", "there is no datetime constructor; write a literal"),
    "eval": Reject("EXP102", "not permitted"),
    "exec": Reject("EXP102", "not permitted"),
    "open": Reject("EXP102", "not permitted"),
    "__import__": Reject("EXP102", "not permitted"),
}

NON_DETERMINISTIC = frozenset({"now", "today", "current"})

ALLOWED_CALLS = frozenset(FUNCTIONS)


def arithmetic(op: str, left: str, right: str) -> Scalar | Reject | None:
    """The result of `left op right`, a rejection, or None when no rule exists."""
    if (op, left, right) in TEMPORAL:
        return TEMPORAL[(op, left, right)]
    if left == "time" or right == "time":
        return NO_TIME_ARITHMETIC
    if op == "%":
        return REMAINDER.get((left, right))
    if op == "+" and (left, right) in STRING_CONCAT:
        return STRING_CONCAT[(left, right)]
    if op == "*" and "string" in (left, right):
        return NO_REPETITION
    table = DIVISION if op == "/" else ARITHMETIC
    if left in NUMERIC and right in NUMERIC:
        return table.get((left, right))
    return None


def comparable(left: str, right: str) -> Scalar | Reject | None:
    """Whether two types may be ordered against each other."""
    if (left, right) in COMPARISON_REJECTS:
        return COMPARISON_REJECTS[(left, right)]
    if "boolean" in (left, right):
        return NOT_ORDERED
    if left == right and left in ORDERED:
        return BOOLEAN
    if left in NUMERIC and right in NUMERIC:
        result = ARITHMETIC.get((left, right))
        return BOOLEAN if isinstance(result, Scalar) else result
    return None


def equatable(left: str, right: str) -> Scalar | Reject | None:
    if left == "boolean" and right == "boolean":
        return BOOLEAN
    return comparable(left, right)


def membership(element: ExprType, container: ExprType) -> Scalar | Reject | None:
    if isinstance(container, Scalar) and container.name == "string":
        return NO_SUBSTRING_IN
    if not isinstance(container, ListOf):
        return None
    if not isinstance(element, Scalar) or not isinstance(container.element, Scalar):
        return None
    result = equatable(element.name, container.element.name)
    return BOOLEAN if isinstance(result, Scalar) else result
