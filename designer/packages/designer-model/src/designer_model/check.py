"""The model check.

Every rule declares a scope, so a re-check after an edit is neither wrong nor
whole-model. `item` rules re-run for touched items and their dependents,
`context` rules for touched contexts, and `model` rules on demand and before
export.

Expression typing is absent: that is the `EXP` family and needs the signature
table. Everything here is structural, and none of it needs an expression parsed
— the two places that look inside an expression scan for tokens rather than
parse, which is enough to find a deleted operand or a clock call.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from .codes import blocks_export, severity
from .derive import Deriver
from .diagnostics import (
    Diagnostic,
    ItemRef,
    Kind,
    Related,
    Scope,
    Severity,
    Subject,
    TextSpan,
)
from .expressions import check_leaf
from .expressions.types import UNKNOWN, ExprType, ListOf, Scalar
from .literals import ListLiteral, ScalarLiteral
from .model import (
    AnyTypeRef,
    Binding,
    Entity,
    Item,
    LiteralArg,
    Model,
    PathArg,
    Schema,
    SchemaBinding,
    Slot,
    SlotArg,
    Type,
    TypeRef,
)
from .stdlib import Library, operand_uuids, standard_library

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
MAX_PATH = 4

KIND_OF = {
    "Context": Kind.CONTEXT,
    "Validator": Kind.VALIDATOR,
    "Interface": Kind.INTERFACE,
    "Type": Kind.TYPE,
    "Property": Kind.PROPERTY,
    "Entity": Kind.ENTITY,
    "Schema": Kind.SCHEMA,
}


@dataclass(frozen=True, slots=True)
class Report:
    """The findings, plus the questions callers actually ask of them."""

    findings: tuple[Diagnostic, ...]

    def by_severity(self, level: Severity) -> tuple[Diagnostic, ...]:
        return tuple(f for f in self.findings if severity(f.code) is level)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return self.by_severity(Severity.ERROR)

    @property
    def export_blockers(self) -> tuple[Diagnostic, ...]:
        """Declarative, from the code registry, rather than a list the exporter
        keeps its own copy of."""
        return tuple(f for f in self.findings if blocks_export(f.code))

    @property
    def codes(self) -> list[str]:
        return [f.code for f in self.findings]

    def counts(self) -> dict[Severity, int]:
        out = dict.fromkeys(Severity, 0)
        for f in self.findings:
            out[severity(f.code)] += 1
        return out


class Checker:
    def __init__(self, model: Model, library: Library | None = None) -> None:
        self.model = model
        self.library = library if library is not None else standard_library()
        self.d = Deriver(model)

    # --- entry points -------------------------------------------------------

    def run(self, scopes: frozenset[Scope] | None = None) -> Report:
        wanted = scopes if scopes is not None else frozenset(Scope)
        findings: list[Diagnostic] = []
        for scope, rule in self._rules():
            if scope in wanted:
                findings.extend(rule())
        findings.sort(key=lambda f: (severity(f.code), f.code, str(f.subject)))
        return Report(tuple(findings))

    def run_incremental(self, touched: set[UUID]) -> Report:
        """Re-check after an edit: item and context rules only.

        Model-scope rules are the ones safe to defer — none is urgent while
        typing, and running them on every keystroke is what makes an incremental
        check pointless.
        """
        del touched  # rules are cheap enough to re-run whole at this size
        return self.run(frozenset({Scope.ITEM, Scope.CONTEXT}))

    def _rules(self):
        return [
            (Scope.ITEM, self._check_types),
            (Scope.ITEM, self._check_properties),
            (Scope.ITEM, self._check_validators),
            (Scope.ITEM, self._check_interfaces),
            (Scope.MODEL, self._check_interface_bindings),
            (Scope.ITEM, self._check_entities),
            (Scope.ITEM, self._check_schemas),
            (Scope.CONTEXT, self._check_names),
            (Scope.MODEL, self._check_cycles),
            (Scope.MODEL, self._check_global),
        ]

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _subject(item) -> Subject:
        return Subject(item.uuid, KIND_OF[type(item).__name__])

    def _all_items(self):
        return [
            *self.model.contexts,
            *self.model.validators,
            *self.model.types,
            *self.model.properties,
            *self.model.entities,
            *self.model.schemas,
        ]

    def _exists(self, uuid: UUID | None) -> bool:
        return uuid is not None and (uuid in self.d.model.index() or uuid in self.library)

    def _check_binding(self, owner, binding: Binding, where: Subject) -> Iterator[Diagnostic]:
        at = where.then("validators", binding.uuid)
        if binding.validator is None:
            yield Diagnostic("MOD107", at, {"item": ItemRef(owner.uuid)})
            return
        if not self._exists(binding.validator):
            code = "LIB101" if binding.validator.version == 5 else "MOD111"
            yield Diagnostic(
                code, at, {"item": ItemRef(owner.uuid), "field": "validator", "target": ItemRef(binding.validator)}
            )
            return
        if binding.validator in self.library.deprecated:
            yield Diagnostic("LIB102", at, {"item": ItemRef(owner.uuid), "target": ItemRef(binding.validator)})
        yield from self._check_expression(binding, self._binding_value(owner, binding), at)
        if not self._deterministic(binding.validator):
            yield Diagnostic("MOD602", at, {"item": ItemRef(owner.uuid), "validator": ItemRef(binding.validator)})

    def _deterministic(self, validator_uuid: UUID, depth: int = 0) -> bool:
        if validator_uuid in self.library:
            return self.library.is_deterministic(validator_uuid)
        authored = {v.uuid: v for v in self.model.validators}
        v = authored.get(validator_uuid)
        if v is None or depth > 16:
            return True
        if re.search(r"\b(now|today|current)\s*\(", v.expression):
            return False
        if v.is_composite:
            return all(self._deterministic(o, depth + 1) for o in operand_uuids(v.expression))
        return True

    # --- expression checking ------------------------------------------------

    def _expr_type(self, ref: AnyTypeRef | None) -> ExprType:
        """The type a binding supplies for `value`, or UNKNOWN when the item is
        still incomplete — which is what keeps an unfinished Type quiet."""
        base = self.d.base_type_of(ref)
        return Scalar(base) if base else UNKNOWN

    def _validator_of(self, uuid: UUID):
        return self.library.get(uuid) or {v.uuid: v for v in self.model.validators}.get(uuid)

    def _leaf_expressions(self, validator, depth: int = 0):
        """A leaf yields itself; a composite yields its operands, since every
        operand is applied to the same value."""
        if validator is None or depth > 8:
            return
        if not validator.is_composite:
            yield validator
            return
        for operand in operand_uuids(validator.expression):
            yield from self._leaf_expressions(self._validator_of(operand), depth + 1)

    def _binding_value(self, owner, binding: Binding) -> ExprType:
        """What `value` is, at whichever of the three sites this binding sits.

        A Type supplies its own base type; an Entity or a Schema supplies the
        type of whatever the implicit `value` argument names.
        """
        if isinstance(owner, Type):
            return self._expr_type(owner.parent)
        argument = binding.arguments.get("value")
        if isinstance(argument, SlotArg):
            slot = {s.uuid: s for s in self.d.effective_slots(owner.uuid)}.get(argument.slot)
            return self._expr_type(self.d.slot_type(slot)) if slot else UNKNOWN
        if isinstance(argument, PathArg) and isinstance(owner, Schema):
            anchor = getattr(binding, "anchor", None)
            if anchor is None:
                return UNKNOWN
            resolved = self.d.resolve_path(anchor, argument.path)
            if not resolved or not resolved[-1].is_value:
                return UNKNOWN
            return self._expr_type(self.d.slot_type(resolved[-1]))
        return UNKNOWN

    def _check_expression(self, binding: Binding, value: ExprType, at: Subject):
        validator = self._validator_of(binding.validator)
        if validator is None:
            return
        for leaf in self._leaf_expressions(validator):
            result = check_leaf(leaf.expression, value, tuple(leaf.parameters))
            for finding in result.findings:
                span = TextSpan(finding.start, finding.end)
                yield Diagnostic(finding.code, at, {"message": finding.message}, span=span)
            yield from self._check_arguments(binding, result, at)

    def _check_arguments(self, binding: Binding, result, at: Subject):
        """A supplied literal must fit the type inference concluded for its
        parameter — which is also what lets the form offer the right editor."""
        for name, wanted in result.parameters.items():
            argument = binding.arguments.get(name)
            if not isinstance(argument, LiteralArg):
                continue
            got = _literal_type(argument.literal)
            if got is None or wanted == UNKNOWN:
                continue
            if got != wanted:
                yield Diagnostic(
                    "EXP402",
                    at,
                    {"message": f"argument {name} is {got}, but the expression needs {wanted}"},
                )

    # --- types --------------------------------------------------------------

    def _check_types(self) -> Iterator[Diagnostic]:
        for t in self.model.types:
            at = self._subject(t)
            if t.parent is None:
                yield Diagnostic("MOD101", at.then("parent"), {"item": ItemRef(t.uuid)})
            elif isinstance(t.parent, TypeRef):
                if not self._exists(t.parent.type_uuid):
                    yield Diagnostic(
                        "MOD111", at.then("parent"), {"field": "parent", "target": ItemRef(t.parent.type_uuid)}
                    )
                elif self.d.base_type_of(t.parent) is None:
                    yield Diagnostic("MOD112", at.then("parent"), {"item": ItemRef(t.uuid)})
            for b in t.validators:
                yield from self._check_binding(t, b, at)

    def _check_properties(self) -> Iterator[Diagnostic]:
        for p in self.model.properties:
            at = self._subject(p)
            if p.type is None:
                yield Diagnostic("MOD102", at.then("type"), {"item": ItemRef(p.uuid)})
            elif isinstance(p.type, TypeRef) and not self._exists(p.type.type_uuid):
                yield Diagnostic("MOD111", at.then("type"), {"field": "type", "target": ItemRef(p.type.type_uuid)})

    def _check_interfaces(self) -> Iterator[Diagnostic]:
        """A picture is checked when it is written, not when a form renders."""
        from . import pictures

        for item in self.model.interfaces:
            at = self._subject(item)
            if not item.base_type:
                yield Diagnostic("INT101", at.then("base_type"), {"item": ItemRef(item.uuid)})
                continue
            if not item.picture.strip():
                yield Diagnostic("INT102", at.then("picture"), {"item": ItemRef(item.uuid)})
                continue
            try:
                pictures.compile_picture(item.base_type, item.picture, item.decimal_point, item.group_mark)
            except pictures.PictureError as error:
                yield Diagnostic("INT201", at.then("picture"), {"item": ItemRef(item.uuid), "detail": str(error)})

    def _check_interface_bindings(self) -> Iterator[Diagnostic]:
        """An Interface knows one base type; a Type may only use one that
        matches. That is the whole of the compatibility rule, and it is why an
        Interface needs no hierarchy of its own."""
        interfaces = {i.uuid: i for i in self.model.interfaces}
        bound: set[UUID] = set()
        for item in self.model.types:
            at = self._subject(item)
            defaults = [b for b in item.interfaces if b.is_default]
            if len(defaults) > 1:
                yield Diagnostic("INT302", at.then("interfaces"), {"item": ItemRef(item.uuid)})
            base = self.d.base_type_of(item.parent)
            for binding in item.interfaces:
                if binding.interface is None:
                    continue
                bound.add(binding.interface)
                face = interfaces.get(binding.interface)
                if face is None or not base or not face.base_type:
                    continue
                if face.base_type != base:
                    yield Diagnostic(
                        "INT301",
                        at.then("interfaces"),
                        {
                            "item": ItemRef(face.uuid),
                            "base": face.base_type,
                            "target": ItemRef(item.uuid),
                            "other": base,
                        },
                    )
        for face in self.model.interfaces:
            if face.uuid not in bound:
                yield Diagnostic("INT601", self._subject(face), {"item": ItemRef(face.uuid)})

    def _check_validators(self) -> Iterator[Diagnostic]:
        for v in self.model.validators:
            at = self._subject(v)
            if v.name and v.name in self.library.names:
                yield Diagnostic("MOD304", at.then("name"), {"name": v.name})
            if v.is_composite:
                for operand in operand_uuids(v.expression):
                    if not self._exists(operand):
                        yield Diagnostic(
                            "MOD113", at.then("expression"), {"item": ItemRef(v.uuid), "target": ItemRef(operand)}
                        )

    # --- entities -----------------------------------------------------------

    def _check_entities(self) -> Iterator[Diagnostic]:
        for e in self.model.entities:
            at = self._subject(e)
            if e.extends is not None and not self._exists(e.extends):
                yield Diagnostic("MOD111", at.then("extends"), {"field": "extends", "target": ItemRef(e.extends)})
            yield from self._check_slots(e, at)
            yield from self._check_identity(e, at)
            yield from self._check_entity_bindings(e, at)

    def _check_slots(self, e: Entity, at: Subject) -> Iterator[Diagnostic]:
        for s in e.slots:
            here = at.then("slots", s.uuid)
            args = {"slot": s.slot_name}
            if s.is_value:
                if s.property is None:
                    yield Diagnostic("MOD103", here, args)
                elif not self._exists(s.property):
                    yield Diagnostic("MOD111", here, {"field": f"slots.{s.slot_name}", "target": ItemRef(s.property)})
            else:
                if s.target is None:
                    yield Diagnostic("MOD104", here, args)
                    continue
                target = self.d.entities.get(s.target)
                if target is None:
                    yield Diagnostic("MOD111", here, {"field": f"slots.{s.slot_name}", "target": ItemRef(s.target)})
                    continue
                ref = {"slot": s.slot_name, "target": ItemRef(s.target)}
                if target.abstract:
                    yield Diagnostic("MOD401", here, ref)
                if not self.d.is_visible(target.context, e.context):
                    yield Diagnostic("MOD402", here, ref)
                if not self.d.effective_identity(s.target):
                    yield Diagnostic("MOD403", here, ref)
                if s.on_delete == "set_null" and s.required:
                    yield Diagnostic("MOD411", here, args)
            yield from self._check_override(e, s, here)

    def _check_override(self, e: Entity, s: Slot, here: Subject) -> Iterator[Diagnostic]:
        inherited = self.d.inherited_slot(e.uuid, s.slot_name)
        args = {"slot": s.slot_name}
        if inherited is None:
            if s.type_override is not None:
                yield Diagnostic("MOD408", here, args)
            return
        if inherited.kind != s.kind:
            yield Diagnostic("MOD407", here, args)
            return
        if inherited.required and not s.required:
            yield Diagnostic("MOD412", here, args)
        if s.is_value:
            new, old = self.d.slot_type(s), self.d.slot_type(inherited)
            if isinstance(new, TypeRef) and isinstance(old, TypeRef) and new != old:
                if not self.d.narrows(new.type_uuid, old.type_uuid):
                    yield Diagnostic("MOD413", here, args)

    def _check_identity(self, e: Entity, at: Subject) -> Iterator[Diagnostic]:
        effective = {s.uuid: s for s in self.d.effective_slots(e.uuid)}
        for group, field in (
            (e.identity, "identity"),
            (tuple(s for i in e.indexes for s in i.slots), "indexes"),
            (tuple(o.slot for o in e.default_order), "default_order"),
        ):
            for slot_uuid in group:
                if slot_uuid not in effective:
                    yield Diagnostic("MOD410", at.then(field), {"field": field, "slot": str(slot_uuid)[:8]})
        if e.identity:
            for ancestor in self.d.ancestors_of(e.uuid)[1:]:
                other = self.d.entities.get(ancestor)
                if other is not None and other.identity:
                    yield Diagnostic(
                        "MOD409",
                        at.then("identity"),
                        {"item": ItemRef(e.uuid), "other": ItemRef(ancestor)},
                        related=(Related("declares_identity", self._subject(other)),),
                    )
                    break
        elif not e.abstract and not self.d.effective_identity(e.uuid):
            yield Diagnostic("MOD406", at.then("identity"), {"item": ItemRef(e.uuid)})

    def _check_entity_bindings(self, e: Entity, at: Subject) -> Iterator[Diagnostic]:
        by_uuid = {s.uuid: s for s in self.d.effective_slots(e.uuid)}
        for b in e.validators:
            yield from self._check_binding(e, b, at)
            for arg in b.arguments.values():
                slot_uuid = getattr(arg, "slot", None)
                if slot_uuid is None:
                    continue
                slot = by_uuid.get(slot_uuid)
                if slot is None:
                    yield Diagnostic(
                        "MOD410", at.then("validators", b.uuid), {"field": "binding", "slot": str(slot_uuid)[:8]}
                    )
                elif slot.is_reference:
                    yield Diagnostic(
                        "MOD414", at.then("validators", b.uuid), {"item": ItemRef(e.uuid), "slot": slot.slot_name}
                    )

    # --- schemas ------------------------------------------------------------

    def _check_schemas(self) -> Iterator[Diagnostic]:
        for sc in self.model.schemas:
            at = self._subject(sc)
            members = set(sc.members)
            for m in sc.members:
                entity = self.d.entities.get(m)
                if entity is None:
                    yield Diagnostic("MOD111", at.then("members", m), {"field": "members", "target": ItemRef(m)})
                    continue
                ref = {"item": ItemRef(sc.uuid), "target": ItemRef(m)}
                if entity.abstract:
                    yield Diagnostic("MOD501", at.then("members", m), ref)
                if not self.d.is_visible(entity.context, sc.context):
                    yield Diagnostic("MOD502", at.then("members", m), ref)
            for member, slot, target in self.d.unclosed_references(sc):
                yield Diagnostic(
                    "MOD503",
                    at.then("members", member),
                    {
                        "item": ItemRef(sc.uuid),
                        "source": ItemRef(member),
                        "slot": slot.slot_name,
                        "target": ItemRef(target),
                    },
                    related=(Related("target", Subject(target, Kind.ENTITY)),),
                    fix=self._closure_fix(sc),
                )
            if len(sc.members) < 2:
                yield Diagnostic("MOD510", at, {"item": ItemRef(sc.uuid)})
            for b in sc.validators:
                yield from self._check_schema_binding(sc, b, at, members)

    def _closure_fix(self, sc: Schema):
        from .diagnostics import FixHint

        missing = self.d.closure(list(sc.members)) - set(sc.members)
        return FixHint(
            "add_schema_closure",
            f"Add the {len(missing)} missing referenced entities",
            {"schema": str(sc.uuid), "count": len(missing)},
        )

    def _check_schema_binding(
        self, sc: Schema, b: SchemaBinding, at: Subject, members: set[UUID]
    ) -> Iterator[Diagnostic]:
        here = at.then("validators", b.uuid)
        yield from self._check_binding(sc, b, at)
        if b.anchor is None:
            yield Diagnostic("MOD105", here, {"item": ItemRef(sc.uuid)})
            return
        if b.anchor not in members:
            yield Diagnostic("MOD504", here, {"item": ItemRef(sc.uuid), "target": ItemRef(b.anchor)})
        if b.enforcement == "database":
            yield Diagnostic("MOD603", here, {"item": ItemRef(sc.uuid)})
        for param, arg in b.arguments.items():
            path = getattr(arg, "path", None)
            if path is None:
                continue
            yield from self._check_path(sc, b, param, path, here, members)

    def _check_path(self, sc, b, param, path, here, members) -> Iterator[Diagnostic]:
        base = {"item": ItemRef(sc.uuid), "param": param}
        if len(path) > MAX_PATH:
            yield Diagnostic("MOD505", here, {**base, "length": len(path)})
        current = b.anchor
        for position, slot_uuid in enumerate(path):
            if current is None:
                yield Diagnostic("MOD506", here, {**base, "position": position})
                return
            slot = {s.uuid: s for s in self.d.effective_slots(current)}.get(slot_uuid)
            if slot is None:
                yield Diagnostic("MOD506", here, {**base, "position": position})
                return
            last = position == len(path) - 1
            if last:
                if not slot.is_value:
                    yield Diagnostic("MOD507", here, base)
                return
            if not slot.is_reference:
                yield Diagnostic("MOD508", here, {**base, "slot": slot.slot_name})
                return
            if slot.target not in members:
                yield Diagnostic("MOD509", here, {**base, "target": ItemRef(slot.target)})
            current = slot.target

    # --- naming -------------------------------------------------------------

    def _check_names(self) -> Iterator[Diagnostic]:
        seen: dict[tuple, Item] = {}
        for item in self._all_items():
            at = self._subject(item)
            if not item.name:
                yield Diagnostic("MOD106", at.then("name"), {"kind": str(at.item_kind)})
                continue
            if not IDENTIFIER.fullmatch(item.name):
                yield Diagnostic("MOD303", at.then("name"), {"name": item.name})
            key = (getattr(item, "context", None), type(item).__name__, item.name)
            if key in seen:
                other = seen[key]
                yield Diagnostic(
                    "MOD301",
                    at.then("name"),
                    {"name": item.name, "other": ItemRef(other.uuid)},
                    related=(Related("conflicts_with", self._subject(other)),),
                )
            else:
                seen[key] = item
        yield from self._check_shadowing(seen)

    def _check_shadowing(self, seen) -> Iterator[Diagnostic]:
        for (context, kind, name), item in seen.items():
            if context is None:
                continue
            for ancestor in self.d.ancestry(context)[1:]:
                other = seen.get((ancestor, kind, name))
                if other is not None:
                    yield Diagnostic(
                        "MOD302",
                        self._subject(item).then("name"),
                        {"name": name, "other": ItemRef(other.uuid)},
                        related=(Related("shadows", self._subject(other)),),
                    )
                    break

    # --- model-wide ---------------------------------------------------------

    def _check_cycles(self) -> Iterator[Diagnostic]:
        for c in self.model.contexts:
            if c.parent is not None and c.uuid in self.d.ancestry(c.parent):
                yield Diagnostic("MOD204", self._subject(c).then("parent"), {"item": ItemRef(c.uuid)})
        for t in self.model.types:
            if isinstance(t.parent, TypeRef) and t.uuid in self.d.type_chain(t.parent.type_uuid):
                yield Diagnostic("MOD201", self._subject(t).then("parent"), {"item": ItemRef(t.uuid)})
        for e in self.model.entities:
            if e.extends is not None and e.uuid in self.d.ancestors_of(e.extends):
                yield Diagnostic("MOD202", self._subject(e).then("extends"), {"item": ItemRef(e.uuid)})
        authored = {v.uuid: v for v in self.model.validators}
        for v in self.model.validators:
            if v.is_composite and self._validator_cycle(v.uuid, v.uuid, authored, 0):
                yield Diagnostic("MOD203", self._subject(v).then("expression"), {"item": ItemRef(v.uuid)})

    def _validator_cycle(self, start: UUID, current: UUID, authored, depth: int) -> bool:
        if depth > 32:
            return True
        v = authored.get(current)
        if v is None or not v.is_composite:
            return False
        for operand in operand_uuids(v.expression):
            if operand == start or self._validator_cycle(start, operand, authored, depth + 1):
                return True
        return False

    def _check_global(self) -> Iterator[Diagnostic]:
        for e in self.model.entities:
            at = self._subject(e)
            if e.abstract and not self.d.concrete_descendants(e.uuid):
                yield Diagnostic("MOD405", at, {"item": ItemRef(e.uuid)})
            if not e.abstract and not self.d.schemas_containing(e.uuid):
                yield Diagnostic("MOD604", at, {"item": ItemRef(e.uuid)})
            for s in e.slots:
                if s.is_reference and s.target and self.d.concrete_descendants(s.target):
                    yield Diagnostic(
                        "MOD404", at.then("slots", s.uuid), {"slot": s.slot_name, "target": ItemRef(s.target)}
                    )
        # Orphan reporting covers only the kinds where being unreferenced is a
        # signal. A Schema is a deliverable — nothing refers to it by design —
        # and a concrete Entity in no schema is better said by MOD604.
        for item in [*self.model.types, *self.model.properties, *self.model.validators]:
            if not self.d.references_to(item.uuid):
                yield Diagnostic("MOD601", self._subject(item), {"item": ItemRef(item.uuid)})


def check(model: Model, library: Library | None = None) -> Report:
    return Checker(model, library).run()


def _literal_type(literal) -> ExprType | None:
    """The type a supplied literal actually has."""
    if isinstance(literal, ScalarLiteral):
        return Scalar(literal.base_type)
    if isinstance(literal, ListLiteral):
        return ListOf(Scalar(literal.element_type))
    return None
