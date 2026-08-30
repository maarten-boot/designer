"""Commands.

Every mutation goes through here, or undo silently desynchronises. The unit is
**one user action**, not one object and not one field: editing three slot rows
is three commands, but a delete with a dozen fixups is one, and so is adding a
schema member with its closure. `Macro` is how a single intention that touches
many objects stays a single step.

Commands live in the domain package rather than the interface, because nothing
here needs a window: a command-line tool or a generator would want the same undo
guarantees.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .model import Binding, Entity, InterfaceBinding, Model, Schema, Slot

DEFAULT_UNDO_LIMIT = 100


class Command(ABC):
    """One user action. `do` must be repeatable after `undo`."""

    label: str = "change"

    @abstractmethod
    def do(self, model: Model) -> None: ...

    @abstractmethod
    def undo(self, model: Model) -> None: ...

    def touches(self) -> set[UUID]:
        """Items this command changed, for the incremental re-check."""
        return set()


def _find(model: Model, uuid: UUID) -> Any:
    item = model.index().get(uuid)
    if item is None:
        raise KeyError(f"no item {uuid}")
    return item


def _collection(model: Model, item: Any) -> list:
    return {
        "Context": model.contexts,
        "Validator": model.validators,
        "Interface": model.interfaces,
        "Type": model.types,
        "Property": model.properties,
        "Entity": model.entities,
        "Schema": model.schemas,
    }[type(item).__name__]


@dataclass
class SetField(Command):
    """Set one field of one item."""

    uuid: UUID
    field_name: str
    new: Any
    old: Any = None
    label: str = "edit"

    def do(self, model: Model) -> None:
        item = _find(model, self.uuid)
        self.old = getattr(item, self.field_name)
        setattr(item, self.field_name, self.new)

    def undo(self, model: Model) -> None:
        setattr(_find(model, self.uuid), self.field_name, self.old)

    def touches(self) -> set[UUID]:
        return {self.uuid}


@dataclass
class SetSlotField(Command):
    entity_uuid: UUID
    slot_uuid: UUID
    field_name: str
    new: Any
    old: Any = None
    label: str = "edit slot"

    def _slot(self, model: Model) -> Slot:
        entity: Entity = _find(model, self.entity_uuid)
        return next(s for s in entity.slots if s.uuid == self.slot_uuid)

    def do(self, model: Model) -> None:
        slot = self._slot(model)
        self.old = getattr(slot, self.field_name)
        setattr(slot, self.field_name, self.new)

    def undo(self, model: Model) -> None:
        setattr(self._slot(model), self.field_name, self.old)

    def touches(self) -> set[UUID]:
        return {self.entity_uuid}


@dataclass
class AddItem(Command):
    item: Any
    label: str = "add"

    def do(self, model: Model) -> None:
        _collection(model, self.item).append(self.item)

    def undo(self, model: Model) -> None:
        _collection(model, self.item).remove(self.item)

    def touches(self) -> set[UUID]:
        return {self.item.uuid}


@dataclass
class RemoveItem(Command):
    """Remove an item, remembering where it sat so undo restores the order."""

    item: Any
    index: int | None = None
    label: str = "delete"

    def do(self, model: Model) -> None:
        collection = _collection(model, self.item)
        self.index = collection.index(self.item)
        collection.pop(self.index)

    def undo(self, model: Model) -> None:
        _collection(model, self.item).insert(self.index, self.item)

    def touches(self) -> set[UUID]:
        return {self.item.uuid}


@dataclass
class AddSlot(Command):
    entity_uuid: UUID
    slot: Slot
    label: str = "add slot"

    def do(self, model: Model) -> None:
        _find(model, self.entity_uuid).slots.append(self.slot)

    def undo(self, model: Model) -> None:
        _find(model, self.entity_uuid).slots.remove(self.slot)

    def touches(self) -> set[UUID]:
        return {self.entity_uuid}


@dataclass
class RemoveSlot(Command):
    entity_uuid: UUID
    slot: Slot
    index: int | None = None
    label: str = "remove slot"

    def do(self, model: Model) -> None:
        slots = _find(model, self.entity_uuid).slots
        self.index = slots.index(self.slot)
        slots.pop(self.index)

    def undo(self, model: Model) -> None:
        _find(model, self.entity_uuid).slots.insert(self.index, self.slot)

    def touches(self) -> set[UUID]:
        return {self.entity_uuid}


@dataclass
class AddBinding(Command):
    owner_uuid: UUID
    binding: Binding
    index: int | None = None
    """Where to put it. Appended when unset.

    Editing a rule replaces it, and a rule that jumped to the end of the list
    every time it was edited would reorder what the author arranged.
    """
    label: str = "add rule"

    def do(self, model: Model) -> None:
        bindings = _find(model, self.owner_uuid).validators
        if self.index is None:
            bindings.append(self.binding)
        else:
            bindings.insert(self.index, self.binding)

    def undo(self, model: Model) -> None:
        _find(model, self.owner_uuid).validators.remove(self.binding)

    def touches(self) -> set[UUID]:
        return {self.owner_uuid}


@dataclass
class AddInterfaceBinding(Command):
    owner_uuid: UUID
    binding: InterfaceBinding
    label: str = "add presentation"

    def do(self, model: Model) -> None:
        _find(model, self.owner_uuid).interfaces.append(self.binding)

    def undo(self, model: Model) -> None:
        _find(model, self.owner_uuid).interfaces.remove(self.binding)


@dataclass
class RemoveInterfaceBinding(Command):
    owner_uuid: UUID
    binding: InterfaceBinding
    index: int | None = None
    label: str = "remove presentation"

    def do(self, model: Model) -> None:
        bindings = _find(model, self.owner_uuid).interfaces
        self.index = bindings.index(self.binding)
        bindings.remove(self.binding)

    def undo(self, model: Model) -> None:
        _find(model, self.owner_uuid).interfaces.insert(self.index or 0, self.binding)


@dataclass
class SetDefaultPresentation(Command):
    """Exactly one default, so choosing one clears the rest.

    One command rather than several, because it is one decision: undoing it
    should put every flag back as it was, not peel them off one at a time.
    """

    owner_uuid: UUID
    binding_uuid: UUID
    old: tuple[bool, ...] = ()
    label: str = "make default"

    def do(self, model: Model) -> None:
        bindings = _find(model, self.owner_uuid).interfaces
        self.old = tuple(b.is_default for b in bindings)
        for binding in bindings:
            binding.is_default = binding.uuid == self.binding_uuid

    def undo(self, model: Model) -> None:
        for binding, was in zip(_find(model, self.owner_uuid).interfaces, self.old, strict=False):
            binding.is_default = was


@dataclass
class RemoveBinding(Command):
    owner_uuid: UUID
    binding: Binding
    index: int | None = None
    label: str = "remove rule"

    def do(self, model: Model) -> None:
        bindings = _find(model, self.owner_uuid).validators
        self.index = bindings.index(self.binding)
        bindings.pop(self.index)

    def undo(self, model: Model) -> None:
        _find(model, self.owner_uuid).validators.insert(self.index, self.binding)

    def touches(self) -> set[UUID]:
        return {self.owner_uuid}


@dataclass
class SetMembers(Command):
    """Replace a Schema's membership.

    One command whether it adds one entity or ten, which is what makes
    closure-on-add a single undo step rather than a maddening sequence.
    """

    schema_uuid: UUID
    new: tuple[UUID, ...]
    old: tuple[UUID, ...] = ()
    label: str = "change membership"

    def do(self, model: Model) -> None:
        schema: Schema = _find(model, self.schema_uuid)
        self.old = schema.members
        schema.members = self.new

    def undo(self, model: Model) -> None:
        _find(model, self.schema_uuid).members = self.old

    def touches(self) -> set[UUID]:
        return {self.schema_uuid}


@dataclass
class Macro(Command):
    """Several commands as one step.

    Undo runs them in reverse, which matters: a delete's fixups must be put back
    before the item they referred to.
    """

    label: str
    commands: list[Command] = field(default_factory=list)

    def do(self, model: Model) -> None:
        for command in self.commands:
            command.do(model)

    def undo(self, model: Model) -> None:
        for command in reversed(self.commands):
            command.undo(model)

    def touches(self) -> set[UUID]:
        out: set[UUID] = set()
        for command in self.commands:
            out |= command.touches()
        return out


class CommandStack:
    """Bounded undo.

    The cap exists because a single delete command can hold an entire Context
    subtree, so an uncapped stack has no bound on memory. It also means a delete
    more than `limit` actions ago is no longer undoable within the session —
    which is why saving keeps one generation of backup.
    """

    def __init__(self, model: Model, limit: int = DEFAULT_UNDO_LIMIT) -> None:
        self.model = model
        self.limit = limit
        self._done: list[Command] = []
        self._undone: list[Command] = []

    def execute(self, command: Command) -> Command:
        command.do(self.model)
        self._done.append(command)
        self._undone.clear()  # a new action discards the redo branch
        while len(self._done) > self.limit:
            self._done.pop(0)
        return command

    def undo(self) -> Command | None:
        if not self._done:
            return None
        command = self._done.pop()
        command.undo(self.model)
        self._undone.append(command)
        return command

    def redo(self) -> Command | None:
        if not self._undone:
            return None
        command = self._undone.pop()
        command.do(self.model)
        self._done.append(command)
        return command

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    @property
    def undo_label(self) -> str | None:
        return self._done[-1].label if self._done else None

    @property
    def redo_label(self) -> str | None:
        return self._undone[-1].label if self._undone else None

    def __len__(self) -> int:
        return len(self._done)
