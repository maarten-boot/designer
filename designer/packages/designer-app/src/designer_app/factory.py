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
from uuid import UUID, uuid4

from designer_model.model import (
    Context,
    Entity,
    Item,
    Property,
    Schema,
    Type,
    Validator,
)

KINDS = ("Context", "Type", "Validator", "Property", "Entity", "Schema")

_CLASSES = {
    "Context": Context,
    "Type": Type,
    "Validator": Validator,
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


def duplicate[ItemT: Item](item: ItemT) -> ItemT:
    """A copy, of the same kind as its original.

    The kind matters to callers: a copied Validator has a context, and `Item`
    alone does not.

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
