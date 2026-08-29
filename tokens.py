"""Tokens, and the two forms of a composite expression.

Composite operands are stored as UUIDs and shown as names (spec §5.2), so the
stored and displayed texts do not share coordinates. The substitution is
token-level rather than parse-level, which is what lets it work on an expression
that does not yet parse — and that matters, because storing source at all was
chosen so a half-written expression can commit.

Every substitution returns a `TokenMap` alongside the text. Diagnostics carry
offsets in the *stored* form, since that is what matches the file, the JSON tab
and any command-line report; the editor translates through the map.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
KEYWORDS = frozenset({"AND", "OR", "XOR", "NOT"})


@dataclass(frozen=True, slots=True)
class Mapping:
    stored: tuple[int, int]
    display: tuple[int, int]


@dataclass(frozen=True, slots=True)
class TokenMap:
    text: str
    mappings: tuple[Mapping, ...]

    def to_display(self, offset: int) -> int:
        """Translate a stored offset into the displayed text."""
        shift = 0
        for m in self.mappings:
            if offset < m.stored[0]:
                break
            if offset <= m.stored[1]:
                return m.display[0]
            shift += (m.display[1] - m.display[0]) - (m.stored[1] - m.stored[0])
        return offset + shift


def operand_uuids(expression: str) -> list[UUID]:
    """The UUIDs a stored composite expression names, in order."""
    return [UUID(m.group(0)) for m in UUID_PATTERN.finditer(expression)]


def unresolved_names(expression: str) -> list[tuple[str, int, int]]:
    """Identifiers in a stored composite that are neither keywords nor UUIDs.

    A name that resolved to nothing on commit is left as written, so storage
    never fails; the checker reports it from here.
    """
    out = []
    for match in IDENTIFIER.finditer(expression):
        if match.group(0) not in KEYWORDS:
            out.append((match.group(0), match.start(), match.end()))
    return out


def to_display(stored: str, names: dict[UUID, str]) -> TokenMap:
    """Stored (UUIDs) to displayed (names)."""
    pieces: list[str] = []
    mappings: list[Mapping] = []
    cursor = 0
    for match in UUID_PATTERN.finditer(stored):
        pieces.append(stored[cursor : match.start()])
        rendered = "".join(pieces)
        uuid = UUID(match.group(0))
        shown = names.get(uuid) or f"<deleted {match.group(0)[:8]}>"
        mappings.append(Mapping((match.start(), match.end()), (len(rendered), len(rendered) + len(shown))))
        pieces.append(shown)
        cursor = match.end()
    pieces.append(stored[cursor:])
    return TokenMap("".join(pieces), tuple(mappings))


def to_stored(display: str, resolve) -> str:
    """Displayed (names) to stored (UUIDs).

    `resolve` maps a name to a UUID or None. An unresolvable name is left as
    written rather than rejected — the commit always succeeds, and the checker
    reports what it could not resolve.
    """
    out: list[str] = []
    cursor = 0
    for match in IDENTIFIER.finditer(display):
        name = match.group(0)
        if name in KEYWORDS:
            continue
        uuid = resolve(name)
        if uuid is None:
            continue
        out.append(display[cursor : match.start()])
        out.append(str(uuid))
        cursor = match.end()
    out.append(display[cursor:])
    return "".join(out)
