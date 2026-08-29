"""The standard library, loaded once into a read-only registry.

Built-ins are global: no Context, visible everywhere, never written to a model
file (spec §5.7). Only references to them are stored, which is why their UUIDs
have to be derivable rather than assigned — see `ids.builtin_id`.

Determinism is derived here by scanning for the clock functions rather than by
storing a flag. The scan is a token match, not a parse, so it works before the
expression checker exists; phase 2's checker supersedes it with the same answer.
"""

from __future__ import annotations

import functools
import pathlib
import re
from uuid import UUID

from .model import Validator
from .persistence import load

DATA = pathlib.Path(__file__).parent / "data" / "stdlib.json"

NON_DETERMINISTIC_CALLS = ("now", "today", "current")
_CALL = re.compile(r"\b(" + "|".join(NON_DETERMINISTIC_CALLS) + r")\s*\(")
_UUID_TOKEN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def operand_uuids(expression: str) -> list[UUID]:
    """The UUIDs a composite expression names, in order of appearance."""
    return [UUID(m.group(0)) for m in _UUID_TOKEN.finditer(expression)]


class Library:
    """The built-in Validators. Read-only by construction: nothing here mutates."""

    def __init__(self, validators: list[Validator], version: int) -> None:
        self.version = version
        self._by_uuid = {v.uuid: v for v in validators}
        self._by_name = {v.name: v for v in validators}
        self.deprecated: frozenset[UUID] = frozenset()

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
        if _CALL.search(validator.expression):
            return False
        if validator.is_composite:
            return all(self.is_deterministic(o, depth + 1) for o in operand_uuids(validator.expression))
        return True


@functools.lru_cache(maxsize=1)
def standard_library() -> Library:
    document = load(DATA)
    return Library(document.validators, document.library_version)
