"""Changing what a schema contains.

Nothing joins a schema by itself, so membership is edited deliberately — and
adding one entity usually means adding more than one, because a member that
references a non-member leaves the schema unclosed.

As with deleting, one walk produces both what the user is shown and the command
that carries it out. Adding a member and its closure is a single undo step: a
fix the user has to undo ten times is worse than no fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .commands import SetMembers
from .derive import Deriver
from .model import Model, Schema

ABSTRACT = "abstract, and abstract entities never materialise"
NOT_VISIBLE = "not visible from this schema's context"
MISSING = "no longer in the model"


@dataclass(frozen=True, slots=True)
class MembershipPlan:
    """What a change to membership would do."""

    schema: UUID
    members_after: tuple[UUID, ...]
    added: tuple[UUID, ...] = ()
    removed: tuple[UUID, ...] = ()
    blocked: tuple[tuple[UUID, str], ...] = ()
    dangling: tuple[tuple[UUID, str, UUID], ...] = ()

    @property
    def changes(self) -> bool:
        return bool(self.added or self.removed)

    @property
    def pulled_in(self) -> tuple[UUID, ...]:
        """Everything added beyond the one that was asked for.

        Shown before the add happens: adding one entity can cascade into ten,
        and the user should see that in advance rather than afterwards.
        """
        return self.added[1:] if len(self.added) > 1 else ()

    def command(self, label: str = "change membership") -> SetMembers:
        return SetMembers(self.schema, self.members_after, label=label)


def _schema(model: Model, schema: UUID) -> Schema:
    found = next((s for s in model.schemas if s.uuid == schema), None)
    if found is None:
        raise KeyError(f"no schema {schema}")
    return found


def addable(model: Model, schema: UUID) -> list[UUID]:
    """Entities that could join: concrete, visible, not already members."""
    target = _schema(model, schema)
    deriver = Deriver(model)
    members = set(target.members)
    return [
        entity.uuid
        for entity in model.entities
        if entity.uuid not in members and not entity.abstract and deriver.is_visible(entity.context, target.context)
    ]


def plan_add(model: Model, schema: UUID, entity: UUID) -> MembershipPlan:
    """Add an entity, and everything its references need.

    A needed entity that is not visible from the schema's context cannot be
    added — the fix for that is a modelling one, moving the shared entity
    higher, which no dialog can do. Such entities are reported as blocked and
    the rest of the add proceeds, leaving the schema unclosed and saying so.
    """
    target = _schema(model, schema)
    deriver = Deriver(model)
    members = set(target.members)
    if entity in members:
        return MembershipPlan(schema, target.members)

    wanted = deriver.closure([entity]) - members
    added: list[UUID] = []
    blocked: list[tuple[UUID, str]] = []
    for candidate in sorted(wanted, key=lambda u: (u != entity, str(u))):
        found = deriver.entities.get(candidate)
        if found is None:
            blocked.append((candidate, MISSING))
        elif found.abstract:
            blocked.append((candidate, ABSTRACT))
        elif not deriver.is_visible(found.context, target.context):
            blocked.append((candidate, NOT_VISIBLE))
        else:
            added.append(candidate)

    if entity in {b[0] for b in blocked}:
        # the entity asked for cannot join, so nothing else should either
        return MembershipPlan(schema, target.members, blocked=tuple(blocked))

    return MembershipPlan(
        schema,
        tuple(target.members) + tuple(added),
        added=tuple(added),
        blocked=tuple(blocked),
    )


def plan_remove(model: Model, schema: UUID, entity: UUID) -> MembershipPlan:
    """Remove an entity, reporting what would then reference outside.

    Removal is checked as well as adding: taking out a member that others point
    at leaves the schema unclosed, and the confirmation names which members
    would dangle.
    """
    target = _schema(model, schema)
    if entity not in target.members:
        return MembershipPlan(schema, target.members)

    after = tuple(m for m in target.members if m != entity)
    probe = Schema(
        uuid=target.uuid,
        name=target.name,
        description=target.description,
        created=target.created,
        modified=target.modified,
        context=target.context,
        members=after,
        validators=target.validators,
    )
    dangling = tuple(
        (member, slot.slot_name, slot_target) for member, slot, slot_target in Deriver(model).unclosed_references(probe)
    )
    return MembershipPlan(schema, after, removed=(entity,), dangling=dangling)


def plan_close(model: Model, schema: UUID) -> MembershipPlan:
    """Add everything the current members reference. The standalone fix, for a
    schema assembled before closure was checked or left open deliberately."""
    target = _schema(model, schema)
    deriver = Deriver(model)
    members = set(target.members)
    wanted = deriver.closure(list(target.members)) - members
    added, blocked = [], []
    for candidate in sorted(wanted, key=str):
        found = deriver.entities.get(candidate)
        if found is None:
            blocked.append((candidate, MISSING))
        elif found.abstract:
            blocked.append((candidate, ABSTRACT))
        elif not deriver.is_visible(found.context, target.context):
            blocked.append((candidate, NOT_VISIBLE))
        else:
            added.append(candidate)
    return MembershipPlan(
        schema,
        tuple(target.members) + tuple(added),
        added=tuple(added),
        blocked=tuple(blocked),
    )
