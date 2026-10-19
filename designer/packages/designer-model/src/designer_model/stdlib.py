"""The standard library, loaded once into a read-only registry.

Built-ins are global: no Context, visible everywhere, never written to a model
file (spec §5.7). Only references to them are stored, which is why their UUIDs
have to be derivable rather than assigned — see `ids.builtin_id`.

Deprecations live beside the library, in `data/deprecations.json`, not inside
it: the library is an ordinary model document and round-trips byte for byte,
and a model document has no place for "do not use this any more". A deprecated
built-in is never removed (spec §5.7) — it still resolves and still works — so
the only things that change are what the interface offers and a note saying why.

Determinism is derived here by scanning for the clock functions rather than by
storing a flag. The scan is a token match, not a parse, so it works before the
expression checker exists; phase 2's checker supersedes it with the same answer.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
from dataclasses import dataclass
from uuid import UUID

from .expressions.sandbox import reads_clock
from .model import Validator
from .persistence import load

DATA = pathlib.Path(__file__).parent / "data" / "stdlib.json"
DEPRECATIONS = pathlib.Path(__file__).parent / "data" / "deprecations.json"

_UUID_TOKEN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def operand_uuids(expression: str) -> list[UUID]:
    """The UUIDs a composite expression names, in order of appearance."""
    return [UUID(m.group(0)) for m in _UUID_TOKEN.finditer(expression)]


@dataclass(frozen=True, slots=True)
class Deprecation:
    since: int
    """The `library_version` that deprecated it."""
    replacement: UUID | None = None
    reason: str = ""


class Library:
    """The built-in Validators. Read-only by construction: nothing here mutates."""

    def __init__(
        self, validators: list[Validator], version: int, deprecations: dict[UUID, Deprecation] | None = None
    ) -> None:
        self.version = version
        self._by_uuid = {v.uuid: v for v in validators}
        self._by_name = {v.name: v for v in validators}
        self.deprecations: dict[UUID, Deprecation] = dict(deprecations or {})

    @property
    def deprecated(self) -> frozenset[UUID]:
        return frozenset(self.deprecations)

    def offered(self, keep: UUID | None = None) -> list[str]:
        """The names a picker offers: every built-in but the deprecated ones,
        sorted. `keep` is the one already chosen, which stays offered so that
        editing an existing rule does not silently change it."""
        return sorted(n for n, v in self._by_name.items() if v.uuid not in self.deprecations or v.uuid == keep)

    def advice(self, uuid: UUID) -> str:
        """What to say about a deprecated built-in: since when, what to use
        instead, and why — as much of that as the library records."""
        found = self.deprecations.get(uuid)
        if found is None:
            return ""
        parts = [f"since library v{found.since}"]
        replacement = self.get(found.replacement) if found.replacement else None
        if replacement is not None:
            parts.append(f"use {replacement.name} instead")
        if found.reason:
            parts.append(found.reason)
        return "; ".join(parts)

    def __len__(self) -> int:
        return len(self._by_uuid)

    def __contains__(self, uuid: UUID) -> bool:
        return uuid in self._by_uuid

    def get(self, uuid: UUID) -> Validator | None:
        return self._by_uuid.get(uuid)

    def by_name(self, name: str) -> Validator | None:
        return self._by_name.get(name)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._by_name)

    def is_deterministic(self, uuid: UUID, depth: int = 0) -> bool:
        """A validator is non-deterministic if it reads the clock, or if any
        operand does. Propagates through composites."""
        validator = self.get(uuid)
        if validator is None or depth > 16:
            return True
        if validator.is_composite:
            return all(self.is_deterministic(o, depth + 1) for o in operand_uuids(validator.expression))
        return not reads_clock(validator.expression)


def load_deprecations(path: pathlib.Path = DEPRECATIONS) -> dict[UUID, Deprecation]:
    """`{"deprecated": [{"validator", "since", "replacement"?, "reason"?}]}`."""
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    return {
        UUID(entry["validator"]): Deprecation(
            since=int(entry["since"]),
            replacement=UUID(entry["replacement"]) if entry.get("replacement") else None,
            reason=entry.get("reason", ""),
        )
        for entry in raw.get("deprecated", [])
    }


@functools.lru_cache(maxsize=1)
def standard_library() -> Library:
    document = load(DATA)
    return Library(document.validators, document.library_version, load_deprecations())
