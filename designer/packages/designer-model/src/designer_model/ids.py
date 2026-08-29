"""Identifiers.

Authored items get random v4 UUIDs. Built-in Validators get deterministic v5
UUIDs so the same name resolves to the same identifier on every installation
(spec §5.7).
"""

from __future__ import annotations

import uuid

NAMESPACE_STDLIB = uuid.uuid5(uuid.NAMESPACE_DNS, "stdlib.designer")


def new_id() -> uuid.UUID:
    """A fresh identifier for an authored item."""
    return uuid.uuid4()


def builtin_id(canonical_name: str) -> uuid.UUID:
    """The identifier of a standard-library Validator."""
    return uuid.uuid5(NAMESPACE_STDLIB, canonical_name)


def is_builtin_id(value: uuid.UUID) -> bool:
    """Built-ins are v5; authored items are v4. Structurally distinguishable."""
    return value.version == 5


def short(value: uuid.UUID) -> str:
    """The eight-character form used in messages and diagnostics (spec §5.3)."""
    return str(value)[:8]
