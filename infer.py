"""Type inference.

Two passes over a binding. First infer: seed `value` with the type the binding
supplies, give each declared parameter a variable, walk the tree and let the
signature tables force each variable. Then check the supplied arguments against
what inference concluded.

Unification is what makes `between` work without annotations. From
`min <= value <= max` with `value: date`, both comparisons force `min` and `max`
to `date`, and the binding form can offer date pickers. It is constraint
propagation rather than full Hindley-Milner — expressions here are a line long
and monomorphic in practice, so binding a variable to the concrete type on the
other side of an operator resolves everything the library contains.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from . import signatures as sig
from .sandbox import Violation, _span, scan
from .types import (
    BOOLEAN,
    NUMERIC,
    STRING,
    UNKNOWN,
    ExprType,
    ListOf,
    Scalar,
    UntypedNumber,
    Var,
    accepts_untyped,
    is_unknown,
    settle,
)

COMPARISONS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
EQUALITIES = {ast.Eq: "==", ast.NotEq: "!="}
BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    message: str
    start: int
    end: int


@dataclass
class Result:
    result: ExprType = UNKNOWN
    parameters: dict[str, ExprType] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    deterministic: bool = True
    used: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.findings


class Inferencer:
    def __init__(self, source: str, value: ExprType, parameters: tuple[str, ...]) -> None:
        self.source = source
        self.value = value
        self.bindings: dict[str, ExprType] = {name: Var(name) for name in parameters}
        if "value" not in self.bindings:
            self.bindings["value"] = value
        else:
            self.bindings["value"] = value
        self.findings: list[Finding] = []
        self.deterministic = True
        self.used: set[str] = set()

    # --- reporting ----------------------------------------------------------

    def report(self, code: str, message: str, node: ast.AST) -> ExprType:
        start, end = _span(node, self.source)
        self.findings.append(Finding(code, message, start, end))
        return UNKNOWN  # poison, so one mistake yields one diagnostic

    def reject(self, reject: sig.Reject, node: ast.AST) -> ExprType:
        return self.report(reject.code, reject.hint, node)

    # --- variables ----------------------------------------------------------

    def resolve(self, t: ExprType) -> ExprType:
        seen = 0
        while isinstance(t, Var) and seen < 8:
            bound = self.bindings.get(t.name)
            if bound is None or bound == t:
                return t
            t, seen = bound, seen + 1
        return t

    def bind(self, var: Var, concrete: ExprType) -> bool:
        """Bind a variable, or refuse when its constraint forbids the type."""
        if isinstance(concrete, (Var, UntypedNumber)) or is_unknown(concrete):
            return True
        if var.constraint is not None and (not isinstance(concrete, Scalar) or concrete.name not in var.constraint):
            return False
        self.bindings[var.name] = concrete
        return True

    def unify(self, left: ExprType, right: ExprType, node: ast.AST) -> None:
        """Push a concrete type across an operator into an open variable."""
        left, right = self.resolve(left), self.resolve(right)
        for var, other in ((left, right), (right, left)):
            if isinstance(var, Var) and not self.bind(var, other):
                allowed = " or ".join(sorted(var.constraint))
                self.report("EXP304", f"this applies to {allowed}, not {other}", node)

    # --- walking ------------------------------------------------------------

    def infer(self, node: ast.AST) -> ExprType:
        method = getattr(self, f"_{type(node).__name__.lower()}", None)
        if method is None:
            return self.report("EXP102", f"{type(node).__name__} is not permitted", node)
        return method(node)

    def _expression(self, node: ast.Expression) -> ExprType:
        return self.infer(node.body)

    def _constant(self, node: ast.Constant) -> ExprType:
        value = node.value
        if isinstance(value, bool):
            return BOOLEAN
        if isinstance(value, int):
            return UntypedNumber(fractional=False)
        if isinstance(value, float):
            return UntypedNumber(fractional=True)
        if isinstance(value, str):
            return STRING
        return self.report("EXP402", f"{value!r} is not a supported literal", node)

    def _list(self, node: ast.List) -> ExprType:
        if not node.elts:
            return ListOf(UNKNOWN)
        element_types = [settle(self.infer(e)) for e in node.elts]
        first = element_types[0]
        if any(t != first for t in element_types[1:]):
            shown = ", ".join(sorted({str(t) for t in element_types}))
            return self.report("EXP401", f"a list literal must be homogeneous; got {shown}", node)
        return ListOf(first)

    _tuple = _list

    def _name(self, node: ast.Name) -> ExprType:
        if node.id in self.bindings:
            self.used.add(node.id)
            return self.resolve(self.bindings[node.id])
        return self.report("EXP403", f"{node.id} is not a parameter of this validator", node)

    def _unaryop(self, node: ast.UnaryOp) -> ExprType:
        operand = self.resolve(self.infer(node.operand))
        if is_unknown(operand):
            return UNKNOWN
        if isinstance(node.op, ast.Not):
            if isinstance(operand, Var):
                self.bind(operand, BOOLEAN)
                return BOOLEAN
            if operand != BOOLEAN:
                return self.reject(sig.NO_TRUTHINESS, node)
            return BOOLEAN
        if isinstance(operand, UntypedNumber):
            return operand
        if isinstance(operand, Scalar) and (operand.name in NUMERIC or operand.name == "duration"):
            return operand
        return self.report(
            "EXP202", f"{operand} does not support unary {'-' if isinstance(node.op, ast.USub) else '+'}", node
        )

    def _boolop(self, node: ast.BoolOp) -> ExprType:
        for value in node.values:
            operand = self.resolve(self.infer(value))
            if is_unknown(operand):
                continue
            if isinstance(operand, Var):
                self.bind(operand, BOOLEAN)
                continue
            if operand != BOOLEAN:
                self.reject(sig.NO_TRUTHINESS, value)
        return BOOLEAN

    def _binop(self, node: ast.BinOp) -> ExprType:
        op = BINOPS.get(type(node.op))
        if op is None:
            code, message = {
                ast.FloorDiv: (sig.NO_FLOOR_DIVISION.code, sig.NO_FLOOR_DIVISION.hint),
            }.get(type(node.op), ("EXP211", f"{type(node.op).__name__} is not supported"))
            return self.report(code, message, node)
        left = self.resolve(self.infer(node.left))
        right = self.resolve(self.infer(node.right))
        return self._apply_binary(op, left, right, node)

    def _apply_binary(self, op: str, left: ExprType, right: ExprType, node) -> ExprType:
        if is_unknown(left) or is_unknown(right):
            return UNKNOWN
        # an untyped literal takes the other side's type
        if isinstance(left, UntypedNumber) and isinstance(right, Scalar):
            left = right if accepts_untyped(right, left) else settle(left)
        if isinstance(right, UntypedNumber) and isinstance(left, Scalar):
            right = left if accepts_untyped(left, right) else settle(right)
        if isinstance(left, UntypedNumber) and isinstance(right, UntypedNumber):
            left, right = settle(left), settle(right)
        if isinstance(left, Var) or isinstance(right, Var):
            self.unify(left, right, node)
            left, right = self.resolve(left), self.resolve(right)
            if isinstance(left, Var) or isinstance(right, Var):
                return UNKNOWN
        if not isinstance(left, Scalar) or not isinstance(right, Scalar):
            return UNKNOWN
        outcome = sig.arithmetic(op, left.name, right.name)
        if outcome is None:
            return self.report("EXP202", f"{left} {op} {right} has no meaning", node)
        if isinstance(outcome, sig.Reject):
            return self.reject(outcome, node)
        return outcome

    def _compare(self, node: ast.Compare) -> ExprType:
        # chained comparisons are one node with several comparators, and half
        # the standard library is written that way
        operands = [self.infer(node.left)] + [self.infer(c) for c in node.comparators]
        for op, left, right in zip(node.ops, operands, operands[1:], strict=False):
            self._apply_comparison(op, left, right, node)
        return BOOLEAN

    def _apply_comparison(self, op, left: ExprType, right: ExprType, node) -> None:
        if isinstance(op, (ast.In, ast.NotIn)):
            self._apply_membership(left, right, node)
            return
        left, right = self.resolve(left), self.resolve(right)
        if is_unknown(left) or is_unknown(right):
            return
        if isinstance(left, UntypedNumber) and isinstance(right, Scalar):
            left = right if accepts_untyped(right, left) else settle(left)
        if isinstance(right, UntypedNumber) and isinstance(left, Scalar):
            right = left if accepts_untyped(left, right) else settle(right)
        if isinstance(left, UntypedNumber) and isinstance(right, UntypedNumber):
            left, right = settle(left), settle(right)
        if isinstance(left, Var) or isinstance(right, Var):
            self.unify(left, right, node)
            left, right = self.resolve(left), self.resolve(right)
            if isinstance(left, Var) or isinstance(right, Var):
                return
        if not isinstance(left, Scalar) or not isinstance(right, Scalar):
            return
        compare = sig.equatable if isinstance(op, tuple(EQUALITIES)) else sig.comparable
        outcome = compare(left.name, right.name)
        if outcome is None:
            symbol = EQUALITIES.get(type(op)) or COMPARISONS.get(type(op), "?")
            self.report("EXP202", f"{left} {symbol} {right} has no meaning", node)
        elif isinstance(outcome, sig.Reject):
            self.reject(outcome, node)

    def _apply_membership(self, element: ExprType, container: ExprType, node) -> None:
        element, container = self.resolve(element), self.resolve(container)
        if is_unknown(element) or is_unknown(container):
            return
        element = settle(element)
        if isinstance(container, Var):
            if isinstance(element, Scalar):
                self.bind(container, ListOf(element))
            return
        outcome = sig.membership(element, container)
        if outcome is None:
            self.report("EXP202", f"{element} in {container} has no meaning", node)
        elif isinstance(outcome, sig.Reject):
            self.reject(outcome, node)

    def _call(self, node: ast.Call) -> ExprType:
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name is None:
            return self.report("EXP101", "only named functions may be called", node)
        if name in sig.REJECTED_FUNCTIONS:
            return self.reject(sig.REJECTED_FUNCTIONS[name], node)
        candidates = sig.FUNCTIONS.get(name)
        if candidates is None:
            return self.report("EXP301", f"there is no function called {name}", node)
        if name in sig.NON_DETERMINISTIC:
            self.deterministic = False
        arguments = [self.resolve(self.infer(a)) for a in node.args]
        for signature in candidates:
            if signature.literal_params:
                for index in signature.literal_params:
                    if index >= len(node.args):
                        continue
                    argument = node.args[index]
                    # a literal, or a parameter the binding will supply one for
                    if isinstance(argument, ast.Constant):
                        continue
                    if isinstance(argument, ast.Name) and argument.id in self.bindings:
                        continue
                    return self.report(
                        "EXP302",
                        f"argument {index + 1} of {name} must be a literal or a parameter, "
                        "so the pattern compiles now rather than at run time",
                        node,
                    )
        return self._resolve_overload(name, candidates, arguments, node)

    def _resolve_overload(self, name, candidates, arguments, node) -> ExprType:
        for signature in candidates:
            matched = self._match(signature, arguments)
            if matched is not None:
                return matched
        # only a genuinely unknowable argument excuses a failure to match; an
        # open variable is bindable, so _match has already had its chance
        if any(is_unknown(a) for a in arguments):
            return UNKNOWN
        shown = ", ".join(str(a) for a in arguments)
        return self.report("EXP301", f"no signature of {name} accepts ({shown})", node)

    def _match(self, signature: sig.Signature, arguments: list[ExprType]) -> ExprType | None:
        if signature.variadic:
            if len(arguments) < len(signature.params):
                return None
            expected = list(signature.params) + [signature.params[-1]] * (len(arguments) - len(signature.params))
        else:
            if len(arguments) != len(signature.params):
                return None
            expected = list(signature.params)

        local: dict[str, ExprType] = {}
        for want, got in zip(expected, arguments, strict=True):
            got = self.resolve(got)
            if is_unknown(got):
                continue
            if isinstance(want, Var):
                concrete = settle(got)
                if signature.constraint is not None:
                    if not isinstance(concrete, Scalar) or concrete.name not in signature.constraint:
                        if isinstance(concrete, Var):
                            continue
                        return None
                previous = local.get(want.name)
                if previous is not None and previous != concrete and not isinstance(concrete, Var):
                    return None
                if not isinstance(concrete, Var):
                    local[want.name] = concrete
                continue
            if isinstance(got, UntypedNumber):
                if not accepts_untyped(want, got):
                    return None
                continue
            if isinstance(got, Var):
                self.bind(got, want)
                continue
            if got != want:
                return None
        result = signature.result
        if isinstance(result, Var):
            resolved = local.get(result.name)
            if resolved is not None:
                return resolved
            if signature.constraint is not None:
                # keep the constraint alive so a later unification can refuse a
                # type this function never produces
                return Var(f"{signature.name}:{result.name}", signature.constraint)
            return UNKNOWN
        return result


UUID_LIKE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")


def check_leaf(source: str, value: ExprType, parameters: tuple[str, ...] = ()) -> Result:
    """Parse, sandbox and type a leaf expression."""
    result = Result()
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        offset = (exc.offset or 1) - 1
        result.findings.append(Finding("EXP112", f"cannot parse: {exc.msg}", offset, offset + 1))
        return result

    violations: list[Violation] = scan(tree, source)
    if violations:
        result.findings.extend(Finding(v.code, v.message, v.start, v.end) for v in violations)
        return result

    inferencer = Inferencer(source, value, parameters)
    inferred = inferencer.resolve(inferencer.infer(tree))
    result.findings.extend(inferencer.findings)
    result.deterministic = inferencer.deterministic
    result.used = inferencer.used
    result.parameters = {
        name: inferencer.resolve(bound) for name, bound in inferencer.bindings.items() if name in parameters
    }
    result.result = inferred

    if not result.findings:
        settled = settle(inferred)
        if not is_unknown(settled) and settled != BOOLEAN:
            result.findings.append(
                Finding("EXP501", f"a validator must produce a boolean, not {settled}", 0, len(source))
            )
    for name in parameters:
        if name not in result.used:
            result.findings.append(Finding("EXP404", f"parameter {name} is never used", 0, len(source)))
    return result


__all__ = ["Finding", "Inferencer", "Result", "check_leaf"]
