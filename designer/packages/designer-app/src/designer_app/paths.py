"""Paths from an anchor.

A cross-entity rule reaches a value by walking reference slots from one member
of a Schema. The rules on that walk (spec §9.3) are strict: at most four
segments, every step but the last a reference, the last a value, and every
entity along the way a member of the same Schema.

All of that is decided here, so the picker can offer only steps that keep the
path legal. An invalid path becomes unconstructible rather than something the
model check reports afterwards — the difference between a control that guides
and one that grades.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from designer_model import Deriver, Model
from designer_model.model import Schema, Slot

LIMIT = 4
"""Four segments. Beyond that a rule is describing a query rather than a
constraint, and the SQL it would need stops being a check."""


@dataclass(frozen=True, slots=True)
class Step:
    """One slot that could come next."""

    slot: UUID
    name: str
    continues: bool
    """True for a reference slot, which the path can go on from. A value slot
    ends the path, because a value is what the rule is finally about."""

    reaches: str = ""


def _members(model: Model, schema: Schema) -> set[UUID]:
    return set(schema.members)


def next_steps(model: Model, schema: Schema, anchor: UUID | None, prefix: tuple[UUID, ...]) -> list[Step]:
    """What may follow the path so far.

    A reference to something outside the Schema is not offered: the rule has to
    be checkable within what ships, and a path leaving the Schema is an error
    the user could not have avoided if it were offered.
    """
    if anchor is None:
        return []
    deriver = Deriver(model)
    current = anchor
    if prefix:
        resolved = deriver.resolve_path(anchor, prefix)
        if not resolved or not resolved[-1].is_reference or resolved[-1].target is None:
            return []
        current = resolved[-1].target

    members = _members(model, schema)
    at_limit = len(prefix) + 1 >= LIMIT
    steps: list[Step] = []
    for slot in sorted(deriver.effective_slots(current), key=lambda s: s.slot_name):
        if slot.is_reference:
            if at_limit or slot.target is None or slot.target not in members:
                continue  # a longer path, or one leaving the schema
            target = deriver.entities.get(slot.target)
            steps.append(Step(slot.uuid, slot.slot_name, True, target.name if target else ""))
        else:
            steps.append(Step(slot.uuid, slot.slot_name, False))
    return steps


def render(model: Model, anchor: UUID | None, path: tuple[UUID, ...]) -> str:
    """The path as a person reads it: `order.customer.country_code`."""
    deriver = Deriver(model)
    entity = deriver.entities.get(anchor) if anchor else None
    head = entity.name if entity else "(no anchor)"
    if not path:
        return head
    resolved = deriver.resolve_path(anchor, path) if anchor else None
    if resolved is None:
        return f"{head}.(does not resolve)"
    return ".".join([head, *(slot.slot_name for slot in resolved)])


def problem(model: Model, schema: Schema, anchor: UUID | None, path: tuple[UUID, ...]) -> str | None:
    """Why a path is not usable, or None when it is.

    The same rules the model check applies, said before the fact rather than
    after — the checker still runs, because a file can arrive from anywhere.
    """
    if anchor is None:
        return "choose an anchor"
    if anchor not in _members(model, schema):
        return "the anchor is not a member of this schema"
    if not path:
        return "choose a value for the rule to apply to"
    if len(path) > LIMIT:
        return f"{len(path)} segments; {LIMIT} is the limit"
    deriver = Deriver(model)
    resolved = deriver.resolve_path(anchor, path)
    if resolved is None:
        return "the path does not resolve"
    for slot in resolved[:-1]:
        if not slot.is_reference:
            return f"the path passes through {slot.slot_name}, which is not a reference"
        if slot.target not in _members(model, schema):
            return f"{slot.slot_name} reaches outside the schema"
    if resolved[-1].is_reference:
        return "the path ends on a reference, not a value"
    return None


def value_slot(model: Model, anchor: UUID | None, path: tuple[UUID, ...]) -> Slot | None:
    """The slot a finished path lands on, whose type the rule is applied to."""
    if anchor is None or not path:
        return None
    resolved = Deriver(model).resolve_path(anchor, path)
    if not resolved or resolved[-1].is_reference:
        return None
    return resolved[-1]


def anchors(model: Model, schema: Schema) -> list[UUID]:
    """Members a rule may be anchored on.

    Concrete only: an abstract entity never becomes a table, so there is
    nothing for the rule to run against.
    """
    deriver = Deriver(model)
    return [
        uuid for uuid in schema.members if (entity := deriver.entities.get(uuid)) is not None and not entity.abstract
    ]
