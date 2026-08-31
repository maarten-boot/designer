"""Making new items.

A new item is created empty — blank name, every reference unset, every list
empty — and completed as the user fills it in. That is not laziness in the
interface; it is the rule the whole model is built on, and it is why an unset
reference is `incomplete` rather than an error.

No tkinter: what a new item looks like the instant it appears is worth pinning
in a test, not discovering by clicking.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from typing import TypeVar
from uuid import UUID, uuid4

from designer_model.model import (
    Context,
    Entity,
    Interface,
    Item,
    Property,
    Schema,
    Type,
    Validator,
)

KINDS = ("Context", "Validator", "Interface", "Type", "Property", "Entity", "Schema")

_CLASSES = {
    "Context": Context,
    "Type": Type,
    "Validator": Validator,
    "Interface": Interface,
    "Property": Property,
    "Entity": Entity,
    "Schema": Schema,
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def new_item(kind: str, context: UUID | None = None) -> Item:
    """An empty item of the given kind, in the active context."""
    if kind not in _CLASSES:
        raise ValueError(f"no such kind: {kind}")
    stamp = _now()
    common = {"uuid": uuid4(), "name": "", "description": "", "created": stamp, "modified": stamp}
    if kind == "Context":
        return Context(**common, parent=context)
    return _CLASSES[kind](**common, context=context)


ItemT = TypeVar("ItemT", bound=Item)


def duplicate(item: ItemT) -> ItemT:  # noqa: UP047
    """A copy, of the same kind as its original.

    The kind matters to callers: a copied Validator has a context, and `Item`
    alone does not.

    Written with a `TypeVar` rather than PEP 695's `def duplicate[ItemT: Item]`,
    which ruff suggests and the 3.12 floor allows. mypy could not parse that
    syntax until 1.11, so the newer spelling made `make types` fail for anyone
    on an older mypy — a check that passes here and fails there is worse than
    no check. One line of older syntax is a cheaper price than a toolchain
    floor for one function.

    The name is left blank rather than made "Copy of X" so it is named
    deliberately — and because a blank name is already a legal, visible,
    incomplete state.
    """
    stamp = _now()
    copy = replace(item, uuid=uuid4(), name="", created=stamp, modified=stamp)
    # lists are shared by `replace`, so a change to the copy would reach the
    # original; give the copy its own
    for attribute in ("slots", "validators"):
        if hasattr(copy, attribute):
            setattr(copy, attribute, list(getattr(item, attribute)))
    return copy


def touch(item: Item) -> None:
    """Record that an item changed.

    `modified` tracks the item's own fields only. It does not propagate to
    items that reference it: a Type is not modified because a validator it uses
    was.
    """
    item.modified = _now()
