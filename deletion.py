"""Deleting.

No delete is refused. Once the model is designed to hold incomplete states and
describe them, a dangling reference is a diagnostic rather than a corruption,
and refusing only forces the user to dismantle references by hand for the same
end state.

One walk produces both the consequences the dialog shows and the commands that
carry them out, so what the user was shown and what happens cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .commands import (
    Command,
    Macro,
    RemoveBinding,
    RemoveItem,
    SetField,
    SetMembers,
    SetSlotField,
)
from .diagnostics import Consequence, ConsequenceKind, ItemRef, Kind, Subject
from .model import Context, Entity, Model, Property, Schema, Type, TypeRef, Validator
from .stdlib import operand_uuids

KIND_OF = {
    "Context": Kind.CONTEXT,
    "Validator": Kind.VALIDATOR,
    "Type": Kind.TYPE,
    "Property": Kind.PROPERTY,
    "Entity": Kind.ENTITY,
    "Schema": Kind.SCHEMA,
}


@dataclass(frozen=True, slots=True)
class DeletePlan:
    """What a delete would do, and the single command that does it."""

    targets: tuple[UUID, ...]
    consequences: tuple[Consequence, ...]
    command: Macro

    def grouped(self) -> dict[ConsequenceKind, list[Consequence]]:
        """The dialog groups by consequence, because '17 items reference this'
        is not a decision aid and '3 schemas lose a member' is."""
        out: dict[ConsequenceKind, list[Consequence]] = {}
        for consequence in self.consequences:
            out.setdefault(consequence.kind, []).append(consequence)
        return out

    @property
    def is_destructive(self) -> bool:
        """True when something loses structure rather than merely a reference.

        Clearing an `extends` takes every inherited slot away from the
        descendant, which changes an Entity's shape. The dialog says so
        prominently.
        """
        return any(c.kind is ConsequenceKind.EXTENSION_CLEARED for c in self.consequences)


def _subject(item) -> Subject:
    return Subject(item.uuid, KIND_OF[type(item).__name__])


def subtree(model: Model, context_uuid: UUID) -> set[UUID]:
    """A Context, its descendant Contexts, and every item inside them."""
    contexts = {context_uuid}
    changed = True
    while changed:
        changed = False
        for context in model.contexts:
            if context.parent in contexts and context.uuid not in contexts:
                contexts.add(context.uuid)
                changed = True
    inside = set(contexts)
    for item in [*model.validators, *model.types, *model.properties, *model.entities, *model.schemas]:
        if item.context in contexts:
            inside.add(item.uuid)
    return inside


def plan_delete(model: Model, target: UUID) -> DeletePlan:
    """Plan the deletion of one item, or of a Context and its whole subtree."""
    item = model.index().get(target)
    if item is None:
        raise KeyError(f"no item {target}")

    targets = subtree(model, target) if isinstance(item, Context) else {target}
    consequences: list[Consequence] = []
    commands: list[Command] = []

    for other in [*model.contexts, *model.validators, *model.types, *model.properties, *model.entities, *model.schemas]:
        if other.uuid in targets:
            continue
        _fixups(model, other, targets, consequences, commands)

    index = model.index()
    for uuid in sorted(targets, key=str):
        removed = index.get(uuid)
        if removed is not None:
            commands.append(RemoveItem(removed))

    label = f"delete {item.name or 'unnamed'}"
    return DeletePlan(tuple(sorted(targets, key=str)), tuple(consequences), Macro(label, commands))


def _fixups(model, other, targets: set[UUID], consequences: list, commands: list) -> None:
    at = _subject(other)

    if isinstance(other, Context) and other.parent in targets:
        consequences.append(Consequence(ConsequenceKind.PARENT_CLEARED, at))
        commands.append(SetField(other.uuid, "parent", None))

    if isinstance(other, Type):
        if isinstance(other.parent, TypeRef) and other.parent.type_uuid in targets:
            consequences.append(Consequence(ConsequenceKind.PARENT_CLEARED, at))
            commands.append(SetField(other.uuid, "parent", None))
        _binding_fixups(other, targets, consequences, commands, at)

    if isinstance(other, Property) and isinstance(other.type, TypeRef) and other.type.type_uuid in targets:
        consequences.append(Consequence(ConsequenceKind.TYPE_CLEARED, at))
        commands.append(SetField(other.uuid, "type", None))

    if isinstance(other, Validator) and other.is_composite:
        # the UUID is deliberately left in the expression text: removing an
        # operand from `A AND B` changes what the rule means, and only the
        # author can decide what it should become
        orphaned = [o for o in operand_uuids(other.expression) if o in targets]
        for operand in orphaned:
            consequences.append(
                Consequence(ConsequenceKind.OPERAND_ORPHANED, at.then("expression"), {"operand": ItemRef(operand)})
            )

    if isinstance(other, Entity):
        if other.extends in targets:
            consequences.append(Consequence(ConsequenceKind.EXTENSION_CLEARED, at))
            commands.append(SetField(other.uuid, "extends", None))
        for slot in other.slots:
            here = at.then("slots", slot.uuid)
            if slot.is_value and slot.property in targets:
                consequences.append(Consequence(ConsequenceKind.PROPERTY_CLEARED, here, {"slot": slot.slot_name}))
                commands.append(SetSlotField(other.uuid, slot.uuid, "property", None))
            if slot.is_value and slot.type_override in targets:
                consequences.append(Consequence(ConsequenceKind.TYPE_CLEARED, here, {"slot": slot.slot_name}))
                commands.append(SetSlotField(other.uuid, slot.uuid, "type_override", None))
            if slot.is_reference and slot.target in targets:
                consequences.append(Consequence(ConsequenceKind.REFERENCE_CLEARED, here, {"slot": slot.slot_name}))
                commands.append(SetSlotField(other.uuid, slot.uuid, "target", None))
        _binding_fixups(other, targets, consequences, commands, at)

    if isinstance(other, Schema):
        lost = [m for m in other.members if m in targets]
        if lost:
            for member in lost:
                consequences.append(Consequence(ConsequenceKind.MEMBERSHIP_REMOVED, at, {"member": ItemRef(member)}))
            commands.append(SetMembers(other.uuid, tuple(m for m in other.members if m not in targets)))
        for binding in list(other.validators):
            if binding.validator in targets:
                consequences.append(Consequence(ConsequenceKind.BINDING_REMOVED, at.then("validators", binding.uuid)))
                commands.append(RemoveBinding(other.uuid, binding))
            elif binding.anchor in targets:
                consequences.append(Consequence(ConsequenceKind.ANCHOR_CLEARED, at.then("validators", binding.uuid)))
                commands.append(SetField(other.uuid, "validators", other.validators))
                # anchors are cleared in place; the binding itself survives
                commands[-1] = _ClearAnchor(other.uuid, binding.uuid)


def _binding_fixups(owner, targets: set[UUID], consequences: list, commands: list, at) -> None:
    for binding in list(owner.validators):
        if binding.validator in targets:
            # a binding without a validator has no meaning, so it goes entirely
            consequences.append(Consequence(ConsequenceKind.BINDING_REMOVED, at.then("validators", binding.uuid)))
            commands.append(RemoveBinding(owner.uuid, binding))


@dataclass
class _ClearAnchor(Command):
    owner_uuid: UUID
    binding_uuid: UUID
    old: UUID | None = None
    label: str = "clear anchor"

    def _binding(self, model: Model):
        owner = model.index()[self.owner_uuid]
        return next(b for b in owner.validators if b.uuid == self.binding_uuid)

    def do(self, model: Model) -> None:
        binding = self._binding(model)
        self.old = binding.anchor
        binding.anchor = None

    def undo(self, model: Model) -> None:
        self._binding(model).anchor = self.old

    def touches(self) -> set[UUID]:
        return {self.owner_uuid}
