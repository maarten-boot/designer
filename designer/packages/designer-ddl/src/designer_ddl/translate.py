"""A rule's expression, from the designer's expression language to SQL.

The export writes each rule in the expression language with its literal
arguments substituted (spec §9.6): `len(value) <= 80`, `quantity >= 1`. This
walks that expression and writes it in a dialect, or raises `Untranslatable`
saying why not. Anything not recognised here is untranslatable by default, so a
construct added to the language later is reported rather than miswritten.

Types are worked out as far as the translation needs them: a column's base
type from the export, a literal's from its spelling, a function's from its
result. That is what tells `+` on strings (concatenation) from `+` on numbers.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping

from .dialects import Column, Dialect, Untranslatable

COMPARISONS = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
ARITHMETIC = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
NUMERIC = {"integer", "decimal", "real"}
NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?")
NOT_YET = {
    "abs", "round", "min", "max", "int", "float", "decimal", "str", "precision", "scale",
    "days", "weeks", "hours", "minutes", "seconds", "total_days", "total_seconds",
}  # fmt: skip
CLOCK = {"now", "today", "current"}


class Translator:
    def __init__(self, source: str, dialect: Dialect, columns: Mapping[str, Column], value: str | None = None):
        """`value` names the column a column rule is about; a table rule names
        its columns directly and has none."""
        self.source = source
        self.d = dialect
        self.columns = columns
        self.value = value

    def sql(self) -> str:
        try:
            tree = ast.parse(self.source.strip(), mode="eval")
        except SyntaxError as error:
            raise Untranslatable(f"the expression does not parse: {error.msg}") from error
        text, kind = self._node(tree.body)
        if kind != "boolean":
            raise Untranslatable(f"the expression is {kind or 'of unknown type'}, not a condition")
        return text

    # --- nodes --------------------------------------------------------------

    def _node(self, node: ast.expr) -> tuple[str, str | None]:
        if isinstance(node, ast.Name):
            return self._name(node.id)
        if isinstance(node, ast.Constant):
            return self._constant(node)
        if isinstance(node, ast.BoolOp):
            word = "AND" if isinstance(node.op, ast.And) else "OR"
            parts = [self._condition(v) for v in node.values]
            return "(" + f" {word} ".join(parts) + ")", "boolean"
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return f"(NOT {self._condition(node.operand)})", "boolean"
            text, kind = self._node(node.operand)
            if kind not in NUMERIC:
                raise Untranslatable("a sign applies only to numbers")
            if isinstance(node.op, ast.USub):
                return f"(-{text})", kind
            if isinstance(node.op, ast.UAdd):
                return text, kind
        if isinstance(node, ast.Compare):
            return self._compare(node), "boolean"
        if isinstance(node, ast.BinOp):
            return self._arithmetic(node)
        if isinstance(node, ast.Call):
            return self._call(node)
        raise Untranslatable(f"{type(node).__name__} has no SQL translation")

    def _condition(self, node: ast.expr) -> str:
        text, kind = self._node(node)
        if kind != "boolean":
            raise Untranslatable("`and`, `or` and `not` take conditions here, not values")
        return text

    def _name(self, name: str) -> tuple[str, str | None]:
        column = self.value if name == "value" and self.value is not None else name
        if column not in self.columns:
            raise Untranslatable(f"{name!r} is not a column of this table")
        found = self.columns[column]
        text = self.d.ident(found.name)
        return (self.d.boolean(text) if found.base == "boolean" else text), found.base

    def _constant(self, node: ast.Constant) -> tuple[str, str | None]:
        value = node.value
        if isinstance(value, bool):
            return (self.d.true if value else self.d.false), "boolean"
        if isinstance(value, (int, float)):
            # the text as written: 0.00 must not become 0.0, nor 1e3 a float
            spelled = ast.get_source_segment(self.source.strip(), node) or repr(value)
            if not NUMBER.fullmatch(spelled):
                raise Untranslatable(f"the number {spelled} has no SQL spelling")
            kind = "integer" if isinstance(value, int) else ("decimal" if "e" not in spelled.lower() else "real")
            return spelled, kind
        if isinstance(value, str):
            return self.d.string(value), "string"
        raise Untranslatable(f"the literal {value!r} has no SQL translation")

    def _compare(self, node: ast.Compare) -> str:
        """Chained comparisons are one node: `a < b < c` is `a < b AND b < c`,
        with `b` written twice (it has no side effects to repeat)."""
        pieces = []
        left = node.left
        for op, right in zip(node.ops, node.comparators, strict=True):
            pieces.append(self._pair(left, op, right))
            left = right
        return pieces[0] if len(pieces) == 1 else "(" + " AND ".join(pieces) + ")"

    def _pair(self, left: ast.expr, op: ast.cmpop, right: ast.expr) -> str:
        if isinstance(op, (ast.In, ast.NotIn)):
            text, _ = self._node(left)
            if not isinstance(right, (ast.List, ast.Tuple)) or not right.elts:
                raise Untranslatable("`in` translates only with a list of values written out")
            options = ", ".join(self._node(e)[0] for e in right.elts)
            word = "IN" if isinstance(op, ast.In) else "NOT IN"
            return f"({text} {word} ({options}))"
        if type(op) not in COMPARISONS:
            raise Untranslatable(f"{type(op).__name__} has no SQL translation")
        # x % n == 0: the one use of % whose meaning does not depend on how the
        # remainder of a negative number is signed (Python floors, SQL truncates)
        for a, b in ((left, right), (right, left)):
            if (
                isinstance(a, ast.BinOp)
                and isinstance(a.op, ast.Mod)
                and isinstance(b, ast.Constant)
                and b.value == 0
                and not isinstance(b.value, bool)
                and isinstance(op, (ast.Eq, ast.NotEq))
            ):
                (x, xk), (n, nk) = self._node(a.left), self._node(a.right)
                if xk not in NUMERIC or nk not in NUMERIC:
                    raise Untranslatable("% applies only to numbers")
                test = self.d.multiple_of(x, n, (xk or "", nk or ""))
                return f"({test})" if isinstance(op, ast.Eq) else f"(NOT ({test}))"
        (a_text, a_kind), (b_text, b_kind) = self._node(left), self._node(right)
        if a_kind == "boolean" and b_kind == "boolean" and not isinstance(op, (ast.Eq, ast.NotEq)):
            raise Untranslatable("booleans are only compared for equality")
        return f"({a_text} {COMPARISONS[type(op)]} {b_text})"

    def _arithmetic(self, node: ast.BinOp) -> tuple[str, str | None]:
        if isinstance(node.op, ast.Mod):
            raise Untranslatable("% translates only as `x % n == 0`: Python and SQL sign a remainder differently")
        if type(node.op) not in ARITHMETIC:
            raise Untranslatable(f"{type(node.op).__name__} has no SQL translation")
        (a, ak), (b, bk) = self._node(node.left), self._node(node.right)
        if isinstance(node.op, ast.Add) and ak == "string" and bk == "string":
            return self.d.concat(a, b), "string"
        if ak not in NUMERIC or bk not in NUMERIC:
            raise Untranslatable(f"arithmetic on {ak} and {bk} has no SQL translation yet")
        if isinstance(node.op, ast.Div) and ak == bk == "integer":
            raise Untranslatable("integer / integer divides exactly in the rule and truncates in SQL")
        kind = "real" if "real" in (ak, bk) else ("decimal" if "decimal" in (ak, bk) else "integer")
        if isinstance(node.op, ast.Div):
            kind = "real" if kind == "real" else "decimal"
        if isinstance(node.op, ast.Div):
            return self.d.divide(a, b), kind
        return f"({a} {ARITHMETIC[type(node.op)]} {b})", kind

    def _call(self, node: ast.Call) -> tuple[str, str | None]:
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise Untranslatable("only plain function calls translate")
        name = node.func.id
        if name in CLOCK:
            raise Untranslatable(f"{name}() reads the clock: a check constraint must not")
        if name in NOT_YET:
            raise Untranslatable(f"{name}() has no SQL translation yet")
        args = [self._node(a) for a in node.args]

        def strings(count: int) -> list[str]:
            if len(args) != count or any(kind != "string" for _, kind in args):
                raise Untranslatable(f"{name}() takes {count} string{'s' if count > 1 else ''}")
            return [text for text, _ in args]

        if name == "len":
            return self.d.length(*strings(1)), "integer"
        if name == "lower":
            return self.d.lower(*strings(1)), "string"
        if name == "upper":
            return self.d.upper(*strings(1)), "string"
        if name == "strip":
            return self.d.strip(*strings(1)), "string"
        if name == "starts_with":
            return self.d.starts_with(*strings(2)), "boolean"
        if name == "ends_with":
            return self.d.ends_with(*strings(2)), "boolean"
        if name == "contains":
            return self.d.contains(*strings(2)), "boolean"
        if name == "regex_full_match":
            text = strings(2)[0]
            pattern = node.args[1]
            if not isinstance(pattern, ast.Constant) or not isinstance(pattern.value, str):
                raise Untranslatable("a pattern translates only when it is written out")
            return self.d.full_match(text, pattern.value), "boolean"
        if name == "is_finite":
            if len(args) != 1 or args[0][1] not in NUMERIC:
                raise Untranslatable("is_finite() takes a number")
            if args[0][1] != "real":
                return self.d.true, "boolean"  # only a real can be NaN or infinite
            return self.d.is_finite(args[0][0]), "boolean"
        raise Untranslatable(f"{name}() has no SQL translation")


def translate(source: str, dialect: Dialect, columns: Mapping[str, Column], value: str | None = None) -> str:
    return Translator(source, dialect, columns, value).sql()
