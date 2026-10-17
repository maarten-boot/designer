"""Evaluation: what a rule says about one value.

Leaf expressions go through `eval`, after the same whitelist walk the checker
uses (`sandbox.scan`) and with no builtins — only the functions the signature
table names, implemented here. That is the one place in the codebase that
evaluates anything, which is what keeps the suppression below targeted.

Composites are evaluated by walking their own parse tree rather than by
translating them to Python, because Python's `and` and `or` short-circuit and
return operands, and Python has no `xor` (see `composite`).

An expression that cannot be evaluated on a value — a type the checker would
reject, a function given something it does not take — raises `EvaluationError`.
That is not a verdict: the caller decides what an unanswerable question means.
"""

from __future__ import annotations

import ast
import datetime as dt
import math
import re
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from .composite import BinOp, Node, Not, Operand, ParseError, parse
from .sandbox import scan
from .tokens import UUID_PATTERN


class EvaluationError(Exception):
    """The expression has no answer for this value."""


def _precision(value: Decimal) -> int:
    """Total digits, as `NUMERIC(p, s)` counts them: `1234.50` is 6, `0.005` is 3."""
    _, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise EvaluationError(f"{value} has no precision")
    if exponent >= 0:
        return len(digits) + exponent
    return max(len(digits), -exponent)


def _scale(value: Decimal) -> int:
    """Digits after the point, trailing zeros included: `1234.50` is 2."""
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise EvaluationError(f"{value} has no scale")
    return max(0, -exponent)


def _round(value, places: int | None = None):
    return round(value) if places is None else round(value, places)


def _functions(value: Any) -> dict[str, Callable[..., Any]]:
    """The signature table's functions. `current()` is the clock in the value's
    own kind — `now()` for a datetime, `today()` for a date — which is what
    unification gives it when the checker types it (signature table §7.4)."""

    def now() -> dt.datetime:
        return dt.datetime.now(dt.UTC)

    def today() -> dt.date:
        return dt.datetime.now(dt.UTC).date()

    def current():
        return today() if isinstance(value, dt.date) and not isinstance(value, dt.datetime) else now()

    return {
        "len": len,
        "lower": str.lower,
        "upper": str.upper,
        "strip": str.strip,
        "starts_with": str.startswith,
        "ends_with": str.endswith,
        "contains": lambda haystack, needle: needle in haystack,
        "regex_full_match": lambda text, pattern: re.fullmatch(pattern, text) is not None,
        "abs": abs,
        "min": min,
        "max": max,
        "round": _round,
        "is_finite": math.isfinite,
        "precision": _precision,
        "scale": _scale,
        "int": int,
        "float": float,
        "str": str,
        "decimal": lambda x: Decimal(x) if isinstance(x, str) else Decimal(int(x)),
        "now": now,
        "today": today,
        "current": current,
        "seconds": lambda n: dt.timedelta(seconds=float(n)),
        "minutes": lambda n: dt.timedelta(minutes=float(n)),
        "hours": lambda n: dt.timedelta(hours=float(n)),
        "days": lambda n: dt.timedelta(days=float(n)),
        "weeks": lambda n: dt.timedelta(weeks=float(n)),
        "total_seconds": dt.timedelta.total_seconds,
        "total_days": lambda d: d.total_seconds() / 86400,
    }


def evaluate_leaf(source: str, value: Any, arguments: Mapping[str, Any] | None = None) -> bool:
    """A leaf expression's verdict on `value`, with its parameters bound."""
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as error:
        raise EvaluationError(f"does not parse: {error.msg}") from error
    violations = scan(tree, source)
    if violations:
        raise EvaluationError(violations[0].message)
    names = {**_functions(value), **(arguments or {}), "value": value}
    try:
        # the whitelist walk above is what makes this defensible: no attribute
        # access, no builtins, and only the functions the signature table names
        result = eval(compile(tree, "<rule>", "eval"), {"__builtins__": {}}, names)  # noqa: S307
    except Exception as error:  # an unanswerable question, whatever raised it
        raise EvaluationError(f"{type(error).__name__}: {error}") from error
    if not isinstance(result, bool):
        raise EvaluationError(f"gave {result!r}, not a yes or no")
    return result


def evaluate_composite(source: str, verdict: Callable[[UUID], bool]) -> bool:
    """A composite's verdict, given a way to ask each operand for its own.

    Every operand is asked, not only the ones a short circuit would reach, so an
    operand that cannot answer is never hidden by the order things were written.
    """
    operands: dict[str, UUID] = {}

    def placeholder(match: re.Match[str]) -> str:
        name = f"_operand{len(operands)}"
        operands[name] = UUID(match.group(0))
        return name

    try:
        tree = parse(UUID_PATTERN.sub(placeholder, source))
    except ParseError as error:
        raise EvaluationError(f"does not parse: {error.message}") from error

    def walk(node: Node) -> bool:
        if isinstance(node, Operand):
            uuid = operands.get(node.token)
            if uuid is None:
                raise EvaluationError(f"{node.token} is not a stored operand")
            return verdict(uuid)
        if isinstance(node, Not):
            return not walk(node.operand)
        if isinstance(node, BinOp):
            left, right = walk(node.left), walk(node.right)
            if node.op == "AND":
                return left and right
            if node.op == "OR":
                return left or right
            return left != right
        raise EvaluationError(f"unexpected {type(node).__name__}")

    return walk(tree)
