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
    SlotArg,
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
    # `replace` shares lists and keeps the identities inside them, so the copy's
    # slots and bindings would be the original's — the same UUIDs that
    # diagnostics, paths and identity address them by. Each gets its own, and
    # whatever named an original slot is pointed at the copy's.
    renamed: dict[UUID, UUID] = {}
    if isinstance(copy, Entity) and isinstance(item, Entity):
        copy.slots = [replace(s, uuid=renamed.setdefault(s.uuid, uuid4())) for s in item.slots]
        copy.identity = tuple(renamed.get(u, u) for u in item.identity)
        copy.indexes = tuple(replace(ix, slots=tuple(renamed.get(u, u) for u in ix.slots)) for ix in item.indexes)
        copy.default_order = tuple(replace(o, slot=renamed.get(o.slot, o.slot)) for o in item.default_order)
    if isinstance(copy, Type | Entity | Schema) and isinstance(item, Type | Entity | Schema):
        copy.validators = [  # type: ignore[assignment]  # a Schema's are SchemaBindings, and replace keeps that
            replace(
                b,
                uuid=uuid4(),
                arguments={
                    k: SlotArg(renamed.get(a.slot, a.slot)) if isinstance(a, SlotArg) else a
                    for k, a in b.arguments.items()
                },
            )
            for b in item.validators
        ]
    if isinstance(copy, Type) and isinstance(item, Type):
        copy.interfaces = [replace(b, uuid=uuid4()) for b in item.interfaces]
    return copy


def touch(item: Item) -> None:
    """Record that an item changed.

    `modified` tracks the item's own fields only. It does not propagate to
    items that reference it: a Type is not modified because a validator it uses
    was.
    """
    item.modified = _now()
