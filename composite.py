"""The composite expression parser.

A separate parser rather than Python's, because Python's `and` and `or`
short-circuit and return operands rather than booleans, and Python has no `xor`
keyword — so evaluating a composite through `eval` would be quietly wrong for
exactly the four operators the language specifies.

Precedence, highest first:

    NOT
    AND
    XOR
    OR

The specification never stated it. This is the ordering every language carrying
all four uses, so `A OR B XOR C` groups as `A OR (B XOR C)`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z_][A-Za-z0-9_-]*)")


class ParseError(Exception):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


class Node:
    pass


@dataclass(frozen=True, slots=True)
class Operand(Node):
    """A leaf: the token naming another Validator, stored as a UUID."""

    token: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Not(Node):
    operand: Node


@dataclass(frozen=True, slots=True)
class BinOp(Node):
    op: str  # AND | OR | XOR
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int
    end: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if match is None:
            if source[position].isspace():
                position += 1
                continue
            raise ParseError(f"unexpected character {source[position]!r}", position)
        tokens.append(Token(match.group(1), match.start(1), match.end(1)))
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token], length: int) -> None:
        self.tokens = tokens
        self.index = 0
        self.length = length

    def peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> Token:
        token = self.peek()
        if token is None:
            raise ParseError("expression ends early", self.length)
        self.index += 1
        return token

    def parse(self) -> Node:
        if not self.tokens:
            raise ParseError("empty expression", 0)
        node = self.or_level()
        rest = self.peek()
        if rest is not None:
            raise ParseError(f"unexpected {rest.text!r}", rest.start)
        return node

    def or_level(self) -> Node:
        node = self.xor_level()
        while (token := self.peek()) is not None and token.text == "OR":
            self.take()
            node = BinOp("OR", node, self.xor_level())
        return node

    def xor_level(self) -> Node:
        node = self.and_level()
        while (token := self.peek()) is not None and token.text == "XOR":
            self.take()
            node = BinOp("XOR", node, self.and_level())
        return node

    def and_level(self) -> Node:
        node = self.unary()
        while (token := self.peek()) is not None and token.text == "AND":
            self.take()
            node = BinOp("AND", node, self.unary())
        return node

    def unary(self) -> Node:
        token = self.peek()
        if token is not None and token.text == "NOT":
            self.take()
            return Not(self.unary())
        return self.primary()

    def primary(self) -> Node:
        token = self.take()
        if token.text == "(":
            node = self.or_level()
            closing = self.peek()
            if closing is None or closing.text != ")":
                raise ParseError("unclosed parenthesis", token.start)
            self.take()
            return node
        if token.text in {"AND", "OR", "XOR", ")"}:
            raise ParseError(f"unexpected {token.text!r}", token.start)
        return Operand(token.text, token.start, token.end)


def parse(source: str) -> Node:
    return _Parser(tokenize(source), len(source)).parse()


def operands(node: Node) -> list[Operand]:
    if isinstance(node, Operand):
        return [node]
    if isinstance(node, Not):
        return operands(node.operand)
    if isinstance(node, BinOp):
        return operands(node.left) + operands(node.right)
    return []


def render(node: Node, name_of) -> str:
    """Back to source, for a round-trip test rather than for storage — storage
    keeps the author's own text (spec §5.2)."""
    if isinstance(node, Operand):
        return name_of(node.token)
    if isinstance(node, Not):
        return f"NOT {render(node.operand, name_of)}"
    if isinstance(node, BinOp):
        return f"({render(node.left, name_of)} {node.op} {render(node.right, name_of)})"
    raise TypeError(node)
