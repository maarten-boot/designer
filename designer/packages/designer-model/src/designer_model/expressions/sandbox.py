"""The whitelist.

Leaf expressions are evaluated with `eval` for v1, but they are parsed and
walked first, and this is the walk that makes that defensible. It is the same
`ast.parse` tree the checker types, with a rejection list attached — which is
why the sandbox and the checker were always going to be one piece of work
rather than two.

Attribute access is banned outright. No case analysis, no exceptions: that is
precisely why the string operations are free functions rather than methods.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .signatures import ALLOWED_CALLS, REJECTED_FUNCTIONS

ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
)

BANNED = {
    ast.Attribute: ("EXP101", "attribute access is not permitted"),
    ast.Subscript: ("EXP103", "subscripting is not permitted"),
    ast.Lambda: ("EXP104", "lambdas are not permitted"),
    ast.ListComp: ("EXP105", "comprehensions are not permitted"),
    ast.SetComp: ("EXP105", "comprehensions are not permitted"),
    ast.DictComp: ("EXP105", "comprehensions are not permitted"),
    ast.GeneratorExp: ("EXP105", "comprehensions are not permitted"),
    ast.IfExp: ("EXP106", "conditional expressions are not permitted"),
    ast.NamedExpr: ("EXP107", "assignment is not permitted"),
    ast.Await: ("EXP108", "await is not permitted"),
    ast.JoinedStr: ("EXP109", "f-strings are not permitted"),
    ast.Starred: ("EXP110", "argument unpacking is not permitted"),
    ast.Is: ("EXP209", "`is` is not supported; use =="),
    ast.IsNot: ("EXP209", "`is not` is not supported; use !="),
    ast.FloorDiv: ("EXP210", "`//` is not supported"),
    ast.Pow: ("EXP211", "exponentiation is not supported"),
}


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    message: str
    start: int
    end: int


def _span(node: ast.AST, source: str) -> tuple[int, int]:
    """Character offsets into the source, which is what a diagnostic carries."""
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    try:
        begin = starts[node.lineno - 1] + node.col_offset
        finish = starts[node.end_lineno - 1] + node.end_col_offset
    except (AttributeError, IndexError):
        return (0, len(source))
    return (begin, finish)


def scan(tree: ast.AST, source: str) -> list[Violation]:
    """Every disallowed construct, not just the first — one pass should tell
    the author everything wrong with the expression."""
    found: list[Violation] = []
    for node in ast.walk(tree):
        for banned, (code, message) in BANNED.items():
            if isinstance(node, banned):
                start, end = _span(node, source)
                found.append(Violation(code, message, start, end))
                break
        else:
            if isinstance(node, ast.Call):
                found.extend(_check_call(node, source))
            elif not isinstance(node, ALLOWED_NODES):
                start, end = _span(node, source)
                found.append(Violation("EXP102", f"{type(node).__name__} is not permitted", start, end))
    return found


def _check_call(node: ast.Call, source: str) -> list[Violation]:
    start, end = _span(node, source)
    if node.keywords:
        return [Violation("EXP111", "keyword arguments are not permitted", start, end)]
    if not isinstance(node.func, ast.Name):
        return [Violation("EXP101", "only named functions may be called", start, end)]
    name = node.func.id
    if name in REJECTED_FUNCTIONS:
        reject = REJECTED_FUNCTIONS[name]
        return [Violation(reject.code, f"{name}: {reject.hint}", start, end)]
    if name not in ALLOWED_CALLS:
        return [Violation("EXP301", f"there is no function called {name}", start, end)]
    return []
