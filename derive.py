"""Derived facts.

Nothing here is stored. The base type of a Type, the effective slots of an
Entity, whether one Type narrows another and whether a Schema is closed are all
computed from what the document holds, so they cannot go stale.

Every walk is depth-limited rather than cycle-detecting, because a cyclic model
is legal to load (the model check reports it) and must not hang the caller.
"""

from __future__ import annotations

from uuid import UUID

from .model import AnyTypeRef, BaseTypeRef, Entity, Model, Schema, Slot, TypeRef

MAX_DEPTH = 64


class Deriver:
    def __init__(self, model: Model) -> None:
        self.model = model
        self.types = {t.uuid: t for t in model.types}
        self.properties = {p.uuid: p for p in model.properties}
        self.entities = {e.uuid: e for e in model.entities}
        self.contexts = {c.uuid: c for c in model.contexts}
        self.schemas = {s.uuid: s for s in model.schemas}

    # --- contexts -----------------------------------------------------------

    def ancestry(self, context: UUID | None) -> list[UUID]:
        """A context and its ancestors, nearest first."""
        out: list[UUID] = []
        cur, depth = context, 0
        while cur is not None and depth < MAX_DEPTH:
            if cur in out:  # cyclic parents: stop, the check reports it
                break
            out.append(cur)
            ctx = self.contexts.get(cur)
            cur = ctx.parent if ctx else None
            depth += 1
        return out

    def is_visible(self, item_context: UUID | None, from_context: UUID | None) -> bool:
        """Lexical scoping: an item is visible from its own Context or any
        ancestor of the observer's (spec §10.1)."""
        if item_context is None:
            return True  # BaseTypes and built-ins have no Context
        return item_context in self.ancestry(from_context)

    # --- types --------------------------------------------------------------

    def type_chain(self, type_uuid: UUID) -> list[UUID]:
        """A Type and its ancestors, nearest first. Stops at a BaseType."""
        out: list[UUID] = []
        cur, depth = type_uuid, 0
        while cur is not None and depth < MAX_DEPTH:
            if cur in out:
                break
            out.append(cur)
            t = self.types.get(cur)
            parent = t.parent if t else None
            cur = parent.type_uuid if isinstance(parent, TypeRef) else None
            depth += 1
        return out

    def base_type_of(self, ref: AnyTypeRef | None) -> str | None:
        """The BaseType a reference bottoms out at, or None when incomplete."""
        cur, depth = ref, 0
        seen: set[UUID] = set()
        while cur is not None and depth < MAX_DEPTH:
            if isinstance(cur, BaseTypeRef):
                return cur.base_type
            if cur.type_uuid in seen:
                return None
            seen.add(cur.type_uuid)
            t = self.types.get(cur.type_uuid)
            if t is None:
                return None
            cur = t.parent
            depth += 1
        return None

    def narrows(self, candidate: UUID, base: UUID) -> bool:
        """True when `candidate` restricts `base` — that is, `base` appears in
        the candidate's parent chain (spec §6)."""
        return base in self.type_chain(candidate)

    # --- entities -----------------------------------------------------------

    def effective_slots(self, entity_uuid: UUID) -> list[Slot]:
        """Inherited slots first, then the Entity's own; a slot with the same
        name overrides rather than duplicates (spec §8.1)."""
        return list(self._effective_slots(entity_uuid, set()).values())

    def _effective_slots(self, entity_uuid: UUID, seen: set[UUID]) -> dict[str, Slot]:
        entity = self.entities.get(entity_uuid)
        if entity is None or entity_uuid in seen:
            return {}
        seen.add(entity_uuid)
        out = self._effective_slots(entity.extends, seen) if entity.extends else {}
        for slot in entity.slots:
            out[slot.slot_name] = slot
        return out

    def inherited_slot(self, entity_uuid: UUID, slot_name: str) -> Slot | None:
        """The slot this Entity's own slot of that name overrides, if any."""
        entity = self.entities.get(entity_uuid)
        if entity is None or entity.extends is None:
            return None
        return self._effective_slots(entity.extends, set()).get(slot_name)

    def effective_identity(self, entity_uuid: UUID) -> tuple[UUID, ...]:
        """Identity is declared once in a chain and inherited below (spec §8.1)."""
        cur, depth = entity_uuid, 0
        while cur is not None and depth < MAX_DEPTH:
            entity = self.entities.get(cur)
            if entity is None:
                return ()
            if entity.identity:
                return entity.identity
            cur = entity.extends
            depth += 1
        return ()

    def ancestors_of(self, entity_uuid: UUID) -> list[UUID]:
        out: list[UUID] = []
        cur, depth = entity_uuid, 0
        while cur is not None and depth < MAX_DEPTH:
            if cur in out:
                break
            out.append(cur)
            entity = self.entities.get(cur)
            cur = entity.extends if entity else None
            depth += 1
        return out

    def concrete_descendants(self, entity_uuid: UUID) -> list[UUID]:
        return [
            e.uuid
            for e in self.model.entities
            if not e.abstract and e.uuid != entity_uuid and entity_uuid in self.ancestors_of(e.uuid)
        ]

    def slot_type(self, slot: Slot) -> AnyTypeRef | None:
        """A value slot's Type: its override, or its Property's."""
        if not slot.is_value:
            return None
        if slot.type_override is not None:
            return TypeRef(slot.type_override)
        prop = self.properties.get(slot.property) if slot.property else None
        return prop.type if prop else None

    # --- schemas ------------------------------------------------------------

    def reference_targets(self, entity_uuid: UUID) -> set[UUID]:
        return {s.target for s in self.effective_slots(entity_uuid) if s.is_reference and s.target}

    def unclosed_references(self, schema: Schema) -> list[tuple[UUID, Slot, UUID]]:
        """Member references that point outside the Schema (spec §9.2)."""
        members = set(schema.members)
        out = []
        for member in schema.members:
            for slot in self.effective_slots(member):
                if slot.is_reference and slot.target and slot.target not in members:
                    out.append((member, slot, slot.target))
        return out

    def closure(self, seeds: list[UUID]) -> set[UUID]:
        """The transitive reference closure of some entities. Reference cycles
        are normal, so the walk carries a visited set (spec §9.2)."""
        found: set[UUID] = set()
        stack = list(seeds)
        while stack:
            current = stack.pop()
            if current in found or current not in self.entities:
                continue
            found.add(current)
            stack.extend(self.reference_targets(current))
        return found

    def schemas_containing(self, entity_uuid: UUID) -> list[Schema]:
        """Membership is non-exclusive, so this can return several (spec §9.1)."""
        return [s for s in self.model.schemas if entity_uuid in s.members]

    def resolve_path(self, anchor: UUID, path: tuple[UUID, ...]) -> list[Slot] | None:
        """Walk a Schema validator path, or None if it does not resolve.

        Structural resolution only: this says the route exists, not that it
        obeys the rules in spec §9.3, which the model check reports on.
        """
        resolved: list[Slot] = []
        current: UUID | None = anchor
        for slot_uuid in path:
            if current is None:
                return None
            by_uuid = {s.uuid: s for s in self.effective_slots(current)}
            slot = by_uuid.get(slot_uuid)
            if slot is None:
                return None
            resolved.append(slot)
            current = slot.target if slot.is_reference else None
        return resolved

    # --- back-references ----------------------------------------------------

    def references_to(self, target: UUID) -> list[tuple[UUID, str]]:
        """Every item referring to this one, with the field that does it.

        Drives the delete impact dialog and the incremental re-check scope.
        """
        out: list[tuple[UUID, str]] = []
        for t in self.model.types:
            if isinstance(t.parent, TypeRef) and t.parent.type_uuid == target:
                out.append((t.uuid, "parent"))
            out.extend((t.uuid, "validators") for b in t.validators if b.validator == target)
        for p in self.model.properties:
            if isinstance(p.type, TypeRef) and p.type.type_uuid == target:
                out.append((p.uuid, "type"))
        for e in self.model.entities:
            if e.extends == target:
                out.append((e.uuid, "extends"))
            for s in e.slots:
                if s.property == target or s.target == target or s.type_override == target:
                    out.append((e.uuid, f"slots.{s.slot_name}"))
            out.extend((e.uuid, "validators") for b in e.validators if b.validator == target)
        for sc in self.model.schemas:
            if target in sc.members:
                out.append((sc.uuid, "members"))
            for b in sc.validators:
                if b.validator == target or b.anchor == target:
                    out.append((sc.uuid, "validators"))
        for item in [
            *self.model.validators,
            *self.model.types,
            *self.model.properties,
            *self.model.entities,
            *self.model.schemas,
        ]:
            if getattr(item, "context", None) == target:
                out.append((item.uuid, "context"))
        for c in self.model.contexts:
            if c.parent == target:
                out.append((c.uuid, "parent"))
        return out


def entity_is_concrete(entity: Entity) -> bool:
    return not entity.abstract
