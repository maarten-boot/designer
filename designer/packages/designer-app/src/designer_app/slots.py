"""Editing slots.

A slot is small but fiddly: it is one of two kinds, its type comes from a
Property or from an override, and a slot that overrides an inherited one may
only narrow it. All of that is decided here rather than in the dialog, so it can
be tested without a display.

A draft is what the dialog collects. Turning one into commands is separate,
because the rules about what a draft may say — an override must narrow, a
required slot may not be set null on delete — are worth stating once and
checking in a test.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from designer_model import Deriver, Model
from designer_model.commands import AddSlot, Command, Macro, RemoveSlot, SetSlotField
from designer_model.literals import Literal, ScalarLiteral
from designer_model.model import BaseTypeRef, Entity, Slot, TypeRef

VALUE = "value"
REFERENCE = "reference"
ON_DELETE = ("restrict", "cascade", "set_null")


class SlotError(ValueError):
    """A draft that cannot be applied, with a reason worth showing."""


@dataclass
class SlotDraft:
    """What the dialog collected. Not yet a slot."""

    slot_name: str = ""
    kind: str = VALUE
    required: bool = True
    property: UUID | None = None
    default_text: str = ""
    type_override: UUID | None = None
    target: UUID | None = None
    inverse_name: str = ""
    on_delete: str = "restrict"

    @classmethod
    def of(cls, slot: Slot) -> SlotDraft:
        return cls(
            slot_name=slot.slot_name,
            kind=slot.kind,
            required=slot.required,
            property=slot.property,
            default_text=default_as_text(slot.default),
            type_override=slot.type_override,
            target=slot.target,
            inverse_name=slot.inverse_name or "",
            on_delete=slot.on_delete,
        )


# --- defaults ----------------------------------------------------------------


def default_as_text(literal: Literal | None) -> str:
    if literal is None:
        return ""
    value = getattr(literal, "value", "")
    return str(value)


def parse_default(base_type: str | None, text: str) -> Literal | None:
    """A typed literal from what was typed, or a reason it is not one.

    The base type decides how to read it, which is why a slot with no type yet
    cannot take a default: there would be nothing to read it as.
    """
    text = text.strip()
    if not text:
        return None
    if base_type is None:
        raise SlotError("give the slot a type before a default")
    try:
        if base_type == "integer":
            return ScalarLiteral(base_type, int(text))
        if base_type == "real":
            return ScalarLiteral(base_type, float(text))
        if base_type == "decimal":
            return ScalarLiteral(base_type, Decimal(text))
        if base_type == "boolean":
            lowered = text.lower()
            if lowered not in {"true", "false"}:
                raise SlotError("a boolean default is true or false")
            return ScalarLiteral(base_type, lowered == "true")
        if base_type == "string":
            return ScalarLiteral(base_type, text)
        if base_type == "date":
            return ScalarLiteral(base_type, dt.date.fromisoformat(text))
        if base_type == "time":
            return ScalarLiteral(base_type, dt.time.fromisoformat(text))
        if base_type == "datetime":
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise SlotError("a datetime needs a timezone; UTC is expected")
            return ScalarLiteral(base_type, parsed.astimezone(dt.UTC))
    except (ValueError, InvalidOperation) as error:
        raise SlotError(f"{text!r} is not a {base_type}: {error}") from error
    raise SlotError(f"no default can be written for {base_type}")


# --- checking a draft --------------------------------------------------------


def check(
    model: Model,
    entity: Entity,
    draft: SlotDraft,
    inherited: Slot | None,
    editing: Slot | None = None,
) -> None:
    """Refuse a draft that cannot be a slot, saying why.

    These are the rules a dialog can enforce before anything happens. The model
    check catches them afterwards too — it has to, since a file can arrive from
    anywhere — but being told at the point of the mistake is worth more.
    """
    deriver = Deriver(model)
    if not draft.slot_name.strip():
        raise SlotError("a slot needs a name")

    # the slot being edited is not a clash with itself, and an override's name
    # matches an *inherited* slot, which is not among this entity's own
    others = {slot.slot_name for slot in entity.slots if slot is not editing}
    if draft.slot_name.strip() in others:
        raise SlotError(f"this entity already has a slot called {draft.slot_name}")

    if draft.kind == REFERENCE:
        # an unset target is allowed — an item is filled in as it is made — but
        # returning here along with it once let an override change the kind of
        # the slot it was overriding
        if draft.target is not None:
            target = deriver.entities.get(draft.target)
            if target is None:
                raise SlotError("that entity is not in the model")
            if target.abstract:
                raise SlotError(f"{target.name} is abstract and has no table for a reference to point at")
            # no check for an identity on the target: it may not have one yet,
            # and refusing here made every new entity unreferenceable. The
            # model check reports it, which is where incompleteness belongs.
        if draft.on_delete == "set_null" and draft.required:
            raise SlotError("a required slot cannot be set null when its target goes")

    if inherited is not None:
        if inherited.kind != draft.kind:
            raise SlotError("an override cannot change the kind of slot")
        if inherited.required and not draft.required:
            raise SlotError("an override cannot make a required slot optional")
        if draft.kind == VALUE:
            new = (
                TypeRef(draft.type_override) if draft.type_override else deriver.slot_type(_as_slot(draft, uuid4(), 0))
            )
            old = deriver.slot_type(inherited)
            if isinstance(new, TypeRef) and isinstance(old, TypeRef) and new != old:
                if not deriver.narrows(new.type_uuid, old.type_uuid):
                    raise SlotError("an override must narrow the inherited type, not widen it")


def _as_slot(draft: SlotDraft, uuid: UUID, position: int) -> Slot:
    slot = Slot(uuid, draft.slot_name.strip(), draft.kind, draft.required, position)
    if draft.kind == VALUE:
        slot.property = draft.property
        slot.type_override = draft.type_override
    else:
        slot.target = draft.target
        slot.inverse_name = draft.inverse_name.strip() or None
        slot.on_delete = draft.on_delete
    return slot


def base_type_of_draft(model: Model, draft: SlotDraft) -> str | None:
    deriver = Deriver(model)
    if draft.type_override is not None:
        return deriver.base_type_of(TypeRef(draft.type_override))
    prop = next((p for p in model.properties if p.uuid == draft.property), None)
    return deriver.base_type_of(prop.type) if prop else None


# --- turning a draft into commands -------------------------------------------


def add(model: Model, entity: Entity, draft: SlotDraft, inherited: Slot | None = None) -> Command:
    """A new slot, or an override of an inherited one."""
    check(model, entity, draft, inherited)
    position = 1 + max((slot.position for slot in entity.slots), default=-1)
    slot = _as_slot(draft, uuid4(), position)
    if draft.kind == VALUE:
        slot.default = parse_default(base_type_of_draft(model, draft), draft.default_text)
    label = "override slot" if inherited is not None else f"add slot {slot.slot_name}"
    return AddSlot(entity.uuid, slot, label=label)


def edit(model: Model, entity: Entity, slot: Slot, draft: SlotDraft) -> Command:
    """Every changed field, as one step.

    One user action is one undo step, and editing a slot in a dialog is one
    action however many of its fields moved.
    """
    inherited = Deriver(model).inherited_slot(entity.uuid, slot.slot_name)
    check(model, entity, draft, inherited, editing=slot)
    changes: list[Command] = []
    wanted = _as_slot(draft, slot.uuid, slot.position)
    fields = (
        ["slot_name", "required", "property", "type_override"]
        if draft.kind == VALUE
        else ["slot_name", "required", "target", "inverse_name", "on_delete"]
    )
    for name in fields:
        if getattr(wanted, name) != getattr(slot, name):
            changes.append(SetSlotField(entity.uuid, slot.uuid, name, getattr(wanted, name)))
    if draft.kind == VALUE:
        default = parse_default(base_type_of_draft(model, draft), draft.default_text)
        if default != slot.default:
            changes.append(SetSlotField(entity.uuid, slot.uuid, "default", default))
    if not changes:
        return Macro("no change", [])
    return Macro(f"edit slot {slot.slot_name}", changes)


def remove(entity: Entity, slot: Slot) -> Command:
    return RemoveSlot(entity.uuid, slot, label=f"remove slot {slot.slot_name}")


def move(entity: Entity, slot: Slot, delta: int) -> Command:
    """Swap two slots' positions.

    Order is stored, so moving is a real change rather than a view setting.
    """
    ordered = sorted(entity.slots, key=lambda s: s.position)
    index = ordered.index(slot)
    target = index + delta
    if not 0 <= target < len(ordered):
        return Macro("no change", [])
    other = ordered[target]
    return Macro(
        f"move slot {slot.slot_name}",
        [
            SetSlotField(entity.uuid, slot.uuid, "position", other.position),
            SetSlotField(entity.uuid, other.uuid, "position", slot.position),
        ],
    )


def named_after_its_property(model: Model, entity: Entity, draft: SlotDraft) -> SlotDraft:
    """Fill a blank slot name from the property it takes.

    The name is usually the property's, so typing it again is a chore — but
    only where that name is free. A second slot on the same property has to be
    named deliberately, because two slots called `amount` cannot both exist and
    guessing which one was meant is not the interface's business.
    """
    if draft.slot_name.strip() or draft.kind != VALUE or draft.property is None:
        return draft
    prop = next((p for p in model.properties if p.uuid == draft.property), None)
    if prop is None or not prop.name:
        return draft
    if any(slot.slot_name == prop.name for slot in Deriver(model).effective_slots(entity.uuid)):
        return draft
    return replace(draft, slot_name=prop.name)


def describes(model: Model, slot: Slot) -> str:
    """The type or target of a slot, for a table cell."""
    deriver = Deriver(model)
    if slot.is_reference:
        target = deriver.entities.get(slot.target) if slot.target else None
        return f"\u2192 {target.name}" if target else "\u2192 (none)"
    reference = deriver.slot_type(slot)
    if isinstance(reference, BaseTypeRef):
        return reference.base_type
    if isinstance(reference, TypeRef):
        found = next((t for t in model.types if t.uuid == reference.type_uuid), None)
        return found.name if found else "(missing)"
    return "(none)"
