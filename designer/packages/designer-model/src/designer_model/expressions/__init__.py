"""Expressions: parse, check, evaluate.

Everything that looks inside an expression goes through this package, and
nothing else in the codebase calls `eval` or `compile`. That is what makes a
single targeted linter suppression correct rather than a blanket disable, and
it is what will make swapping `eval` for a fully sandboxed evaluator a one-file
change.
"""

from .composite import ParseError
from .composite import parse as parse_composite
from .infer import Finding, Result, check_leaf
from .tokens import TokenMap, operand_uuids, to_display, to_stored
from .types import (
    BOOLEAN,
    DATE,
    DATETIME,
    DECIMAL,
    DURATION,
    INTEGER,
    REAL,
    STRING,
    TIME,
    UNKNOWN,
    ExprType,
    ListOf,
    Scalar,
)

__all__ = [
    "BOOLEAN",
    "DATE",
    "DATETIME",
    "DECIMAL",
    "DURATION",
    "INTEGER",
    "REAL",
    "STRING",
    "TIME",
    "UNKNOWN",
    "ExprType",
    "Finding",
    "ListOf",
    "ParseError",
    "Result",
    "Scalar",
    "TokenMap",
    "check_leaf",
    "operand_uuids",
    "parse_composite",
    "to_display",
    "to_stored",
]
