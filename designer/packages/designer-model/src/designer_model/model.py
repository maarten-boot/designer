"""The domain items.

Every reference is a UUID and every required reference is nullable, because an
item is created empty and completed as the user fills it in (spec §3.1). The
model holds broken states and describes them; it does not prevent them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from uuid import UUID

from .literals import Literal

# `Slot` has a field called `property`, which shadows the builtin inside that
# class body. Aliasing it here keeps the field named as the document names it.
_prop = property

# --- references -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaseTypeRef:
    base_type: str


@dataclass(frozen=True, slots=True)
class TypeRef:
    type_uuid: UUID


AnyTypeRef = BaseTypeRef | TypeRef


# --- binding arguments ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiteralArg:
    literal: Literal


@dataclass(frozen=True, slots=True)
class SlotArg:
    slot: UUID


@dataclass(frozen=True, slots=True)
class PathArg:
    """A route from an anchor Entity, stored as slot UUIDs (spec §9.3)."""

    path: tuple[UUID, ...]


Argument = LiteralArg | SlotArg | PathArg


# --- bindings ---------------------------------------------------------------


@dataclass(slots=True)
class Binding:
    """A Validator attached to a Type or an Entity.

    `uuid` exists so a diagnostic or a consequence can address this binding by
    identity rather than by list position, which goes stale on any reorder.
    """

    uuid: UUID
    validator: UUID | None
    arguments: dict[str, Argument] = field(default_factory=dict)
    message: str | None = None


@dataclass(slots=True)
class SchemaBinding(Binding):
    anchor: UUID | None = None
    enforcement: str = "application"


# --- slots ------------------------------------------------------------------


@dataclass(slots=True)
class Slot:
    """The use of a Property, or of another Entity, inside one Entity."""

    uuid: UUID
    slot_name: str
    kind: str  # "value" | "reference"
    required: bool
    position: int
    # value slots
    property: UUID | None = None
    default: Literal | None = None
    type_override: UUID | None = None
    # reference slots
    target: UUID | None = None
    inverse_name: str | None = None
    on_delete: str = "restrict"

    @_prop
    def is_value(self) -> bool:
        return self.kind == "value"

    @_prop
    def is_reference(self) -> bool:
        return self.kind == "reference"


@dataclass(frozen=True, slots=True)
class Index:
    slots: tuple[UUID, ...]
    unique: bool


@dataclass(frozen=True, slots=True)
class OrderTerm:
    slot: UUID
    ascending: bool


# --- items ------------------------------------------------------------------


@dataclass(slots=True)
class Item:
    uuid: UUID
    name: str
    description: str
    created: dt.datetime
    modified: dt.datetime


@dataclass(slots=True)
class Context(Item):
    parent: UUID | None = None


@dataclass(slots=True)
class ContextualItem(Item):
    context: UUID | None = None


@dataclass(slots=True)
class Validator(ContextualItem):
    kind: str = "leaf"  # "leaf" | "composite"
    parameters: tuple[str, ...] = ()
    expression: str = ""
    message: str = ""

    @_prop
    def is_composite(self) -> bool:
        return self.kind == "composite"


@dataclass(slots=True)
class Interface(ContextualItem):
    """How a value is written down for a person, and read back.

    A leaf: no parent, no chain. It knows only about a base type, which is what
    lets any Type over that base type use it. Presentation follows the *Type*
    chain instead (spec appendix §4).

    It never decides whether a value is allowed — that is a Validator, running
    after parsing and before presenting.
    """

    base_type: str = ""
    picture: str = ""
    decimal_point: str = "."
    group_mark: str = ","
    parse_lenient: bool = True
    blank: str = ""


@dataclass(slots=True)
class InterfaceBinding:
    """One Interface attached to a Type.

    No name of its own: the Interface's name identifies it, and two names for
    one thing is an invitation for them to disagree.
    """

    uuid: UUID
    interface: UUID | None = None
    is_default: bool = False


@dataclass(slots=True)
class Type(ContextualItem):
    parent: AnyTypeRef | None = None
    validators: list[Binding] = field(default_factory=list)
    interfaces: list[InterfaceBinding] = field(default_factory=list)


@dataclass(slots=True)
class Property(ContextualItem):
    type: AnyTypeRef | None = None


@dataclass(slots=True)
class Entity(ContextualItem):
    abstract: bool = False
    extends: UUID | None = None
    slots: list[Slot] = field(default_factory=list)
    validators: list[Binding] = field(default_factory=list)
    identity: tuple[UUID, ...] = ()
    indexes: tuple[Index, ...] = ()
    default_order: tuple[OrderTerm, ...] = ()


@dataclass(slots=True)
class Schema(ContextualItem):
    members: tuple[UUID, ...] = ()
    validators: list[SchemaBinding] = field(default_factory=list)


# --- the document -----------------------------------------------------------


@dataclass(slots=True)
class Model:
    schema_version: int = 1
    library_version: int = 1
    contexts: list[Context] = field(default_factory=list)
    validators: list[Validator] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    types: list[Type] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    schemas: list[Schema] = field(default_factory=list)

    def index(self) -> dict[UUID, Item]:
        """Every item by UUID. Rebuilt on demand rather than cached, since a
        stale index is a worse failure than a repeated walk."""
        out: dict[UUID, Item] = {}
        for group in (
            self.contexts,
            self.validators,
            self.interfaces,
            self.types,
            self.properties,
            self.entities,
            self.schemas,
        ):
            for item in group:
                out[item.uuid] = item
        return out

    def slots(self) -> dict[UUID, tuple[Entity, Slot]]:
        return {s.uuid: (e, s) for e in self.entities for s in e.slots}

    def get(self, uuid: UUID | None) -> Item | None:
        return None if uuid is None else self.index().get(uuid)
