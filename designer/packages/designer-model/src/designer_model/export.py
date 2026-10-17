"""Schema export (spec §9.6).

One Schema in, one self-contained document out. Everything a reader would
otherwise have to look up is resolved here: the Type chain is walked and its
rules collected, composites are expanded into one expression, built-ins and
shadowed names are already the Validators they resolve to, and every rule is
sorted into a database check or application enforcement. A reader needs neither
the standard library nor the Context tree, and the document is not a model: it
cannot be loaded back.

The gate is the model check's own: a finding blocks when its code says so
(`blocks_export`) and it is about something the Schema reaches. An unfinished
Type nothing in the Schema uses does not stop the export.

The output is deterministic — no timestamp, every list in model order — so the
same model exports to the same bytes, and a diff of two exports is a diff of
the two models.
"""

from __future__ import annotations

import io
import json
import re
import tokenize
from decimal import Decimal
from typing import Any
from uuid import UUID

from .check import Checker
from .codes import blocks_export, definition
from .derive import MAX_DEPTH, Deriver
from .diagnostics import Diagnostic, Severity, render
from .expressions.composite import BinOp, Not, Operand, ParseError, parse
from .expressions.tokens import UUID_PATTERN
from .ids import builtin_id
from .literals import ListLiteral, Literal, ScalarLiteral, encode
from .model import (
    AnyTypeRef,
    Binding,
    Entity,
    LiteralArg,
    Model,
    PathArg,
    Schema,
    SchemaBinding,
    Slot,
    SlotArg,
    TypeRef,
    Validator,
)
from .stdlib import Library, operand_uuids, standard_library

FORMAT = "designer-schema-export"
FORMAT_VERSION = 1
EXPRESSION_LANGUAGE = "designer-1"

MAX_PRECISION = builtin_id("max_precision")
MAX_SCALE = builtin_id("max_scale")
MAX_LENGTH = builtin_id("max_length")

_CLOCK = re.compile(r"\b(now|today|current)\s*\(")
_COMPOSITE_OPS = {"AND": "and", "OR": "or", "XOR": "!="}


class ExportError(Exception):
    """The Schema cannot be exported. `blockers` names the findings why."""

    def __init__(self, message: str, blockers: tuple[Diagnostic, ...] = ()) -> None:
        super().__init__(message)
        self.blockers = blockers


def export_schema(model: Model, schema_uuid: UUID, library: Library | None = None) -> dict[str, Any]:
    return _Exporter(model, library if library is not None else standard_library()).run(schema_uuid)


def dumps(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


class _Exporter:
    def __init__(self, model: Model, library: Library) -> None:
        self.model = model
        self.library = library
        self.d = Deriver(model)
        self.validators = {v.uuid: v for v in model.validators}
        self.interfaces = {i.uuid: i for i in model.interfaces}
        self.slot_owner = {s.uuid: e for e, s in ((e, s) for e in model.entities for s in e.slots)}

    # --- entry --------------------------------------------------------------

    def run(self, schema_uuid: UUID) -> dict[str, Any]:
        schema = self.d.schemas.get(schema_uuid)
        if schema is None:
            raise ExportError(f"no Schema {schema_uuid}")
        reached = self._reached(schema)
        report = Checker(self.model, self.library).run()
        mine = [f for f in report.findings if f.subject.item_uuid in reached]
        blockers = tuple(f for f in mine if blocks_export(f.code))
        if blockers:
            raise ExportError(f"{len(blockers)} findings block the export of {schema.name}", blockers)
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": {
                "schema_version": self.model.schema_version,
                "library_version": self.library.version,
                "expression_language": EXPRESSION_LANGUAGE,
            },
            "schema": {
                "uuid": str(schema.uuid),
                "name": schema.name,
                "description": schema.description,
                "context": self._context_path(schema.context),
            },
            "warnings": [self._warning(f) for f in mine if definition(f.code).severity is Severity.WARNING],
            "tables": [self._table(self.d.entities[m]) for m in self._table_order(schema)],
            "application": [self._schema_rule(b) for b in schema.validators],
        }

    # --- what the Schema reaches --------------------------------------------

    def _reached(self, schema: Schema) -> set[UUID]:
        """Every item a finding could be about and still matter to this export."""
        out: set[UUID] = {schema.uuid}
        validators: list[UUID] = [b.validator for b in schema.validators if b.validator]
        for member in schema.members:
            for entity_uuid in self.d.ancestors_of(member):
                out.add(entity_uuid)
                entity = self.d.entities.get(entity_uuid)
                if entity is not None:
                    validators.extend(b.validator for b in entity.validators if b.validator)
            for slot in self.d.effective_slots(member):
                if slot.property:
                    out.add(slot.property)
                ref = self.d.slot_type(slot)
                if isinstance(ref, TypeRef):
                    for type_uuid in self.d.type_chain(ref.type_uuid):
                        out.add(type_uuid)
                        t = self.d.types.get(type_uuid)
                        if t is None:
                            continue
                        validators.extend(b.validator for b in t.validators if b.validator)
                        out.update(b.interface for b in t.interfaces if b.interface)
        while validators:
            uuid = validators.pop()
            if uuid in out:
                continue
            out.add(uuid)
            v = self._validator(uuid)
            if v is not None and v.is_composite:
                validators.extend(operand_uuids(v.expression))
        for uuid in list(out):
            item = self.model.get(uuid)
            out.update(self.d.ancestry(getattr(item, "context", None)))
        return out

    def _table_order(self, schema: Schema) -> list[UUID]:
        """Referenced tables first, so a reader can create them in order. Ties
        and reference cycles fall back to the Schema's own member order."""
        members = list(schema.members)
        placed: list[UUID] = []
        while len(placed) < len(members):
            ready = [
                m
                for m in members
                if m not in placed and all(t in placed or t == m for t in self.d.reference_targets(m) if t in members)
            ]
            placed.append(ready[0] if ready else next(m for m in members if m not in placed))
        return placed

    # --- tables -------------------------------------------------------------

    def _table(self, entity: Entity) -> dict[str, Any]:
        slots = self.d.effective_slots(entity.uuid)
        columns: list[dict[str, Any]] = []
        foreign_keys: list[dict[str, Any]] = []
        for slot in slots:
            if slot.is_reference:
                cols, fk = self._reference(entity, slot)
                columns.extend(cols)
                foreign_keys.append(fk)
            else:
                columns.append(self._value_column(entity, slot))
        check, application = self._entity_rules(entity)
        return {
            "name": entity.name,
            "uuid": str(entity.uuid),
            "description": entity.description,
            "context": self._context_path(entity.context),
            "inherits": [self.d.entities[a].name for a in self.d.ancestors_of(entity.uuid)[1:]],
            "columns": columns,
            "primary_key": self._column_names(entity, self.d.effective_identity(entity.uuid)),
            "foreign_keys": foreign_keys,
            "indexes": [
                {"columns": self._column_names(entity, ix.slots), "unique": ix.unique} for ix in entity.indexes
            ],
            "default_order": [
                {"column": name, "ascending": term.ascending}
                for term in entity.default_order
                for name in self._column_names(entity, (term.slot,))
            ],
            "check": check,
            "application": application,
        }

    def _origin(self, entity: Entity, slot: Slot) -> dict[str, str]:
        owner = self.slot_owner.get(slot.uuid)
        if owner is not None and owner.uuid != entity.uuid:
            return {"declared_on": owner.name}
        inherited = self.d.inherited_slot(entity.uuid, slot.slot_name)
        if inherited is not None:
            declared = self.slot_owner.get(inherited.uuid)
            return {"overrides": declared.name if declared else ""}
        return {}

    def _value_column(self, entity: Entity, slot: Slot) -> dict[str, Any]:
        ref = self.d.slot_type(slot)
        prop = self.d.properties.get(slot.property) if slot.property else None
        check, application = self._type_rules(ref)
        return {
            "name": slot.slot_name,
            "uuid": str(slot.uuid),
            **self._origin(entity, slot),
            "property": prop.name if prop else None,
            **self._storage(ref),
            "nullable": not slot.required,
            "default": encode(slot.default) if slot.default is not None else None,
            "check": check,
            "application": application,
            "presentation": self._presentation(ref),
        }

    def _reference(self, entity: Entity, slot: Slot) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """A reference becomes one column per key column of its target, named
        `<slot>_<key column>`. The slot name survives as the relationship."""
        target = self.d.entities[slot.target] if slot.target else None
        if target is None:
            raise ExportError(f"{entity.name}.{slot.slot_name} has no target")
        keys = self._key_columns(target, 0)
        columns = [
            {
                "name": f"{slot.slot_name}_{name}",
                "uuid": str(slot.uuid),
                **self._origin(entity, slot),
                "relationship": slot.slot_name,
                "references": target.name,
                **self._storage(ref),
                "nullable": not slot.required,
                "default": None,
                "check": [],
                "application": [],
                "presentation": None,
            }
            for name, ref in keys
        ]
        fk = {
            "relationship": slot.slot_name,
            "columns": [c["name"] for c in columns],
            "table": target.name,
            "target_columns": [name for name, _ in keys],
            "on_delete": slot.on_delete,
            "inverse_name": slot.inverse_name,
        }
        return columns, fk

    def _key_columns(self, entity: Entity, depth: int) -> list[tuple[str, AnyTypeRef | None]]:
        """The column names and types of an entity's primary key. A key slot
        that is itself a reference expands into the key of what it points at."""
        if depth > MAX_DEPTH:
            raise ExportError(f"the key of {entity.name} does not resolve")
        by_uuid = {s.uuid: s for s in self.d.effective_slots(entity.uuid)}
        out: list[tuple[str, AnyTypeRef | None]] = []
        for uuid in self.d.effective_identity(entity.uuid):
            slot = by_uuid.get(uuid)
            if slot is None:
                raise ExportError(f"the key of {entity.name} names a slot it does not have")
            if slot.is_value:
                out.append((slot.slot_name, self.d.slot_type(slot)))
                continue
            target = self.d.entities.get(slot.target) if slot.target else None
            if target is None:
                raise ExportError(f"{entity.name}.{slot.slot_name} has no target")
            out.extend((f"{slot.slot_name}_{name}", ref) for name, ref in self._key_columns(target, depth + 1))
        if not out:
            raise ExportError(f"{entity.name} has no identity")
        return out

    def _column_names(self, entity: Entity, slot_uuids: tuple[UUID, ...]) -> list[str]:
        by_uuid = {s.uuid: s for s in self.d.effective_slots(entity.uuid)}
        out: list[str] = []
        for uuid in slot_uuids:
            slot = by_uuid.get(uuid)
            if slot is None:
                continue
            if slot.is_value:
                out.append(slot.slot_name)
            else:
                target = self.d.entities[slot.target] if slot.target else None
                if target is not None:
                    out.extend(f"{slot.slot_name}_{name}" for name, _ in self._key_columns(target, 0))
        return out

    # --- storage and presentation -------------------------------------------

    def _storage(self, ref: AnyTypeRef | None) -> dict[str, Any]:
        """The Type as a label, its base type, and the hints a DDL generator
        needs that are carried by rules: length, precision and scale."""
        out: dict[str, Any] = {
            "type": self.d.types[ref.type_uuid].name if isinstance(ref, TypeRef) else None,
            "base": self.d.base_type_of(ref),
        }
        length = self._hint(ref, MAX_LENGTH, "max")
        if length is not None:
            out["length"] = length
        numeric = {
            key: value
            for key, value in (
                ("precision", self._hint(ref, MAX_PRECISION, "p")),
                ("scale", self._hint(ref, MAX_SCALE, "s")),
            )
            if value is not None
        }
        if numeric:
            out["numeric"] = numeric
        return out

    def _hint(self, ref: AnyTypeRef | None, validator: UUID, parameter: str) -> int | None:
        """The tightest literal bound a built-in sets anywhere along the chain.
        Recognised by identity, never by parsing, so a forked copy is not."""
        found: list[int] = []
        for b in self._chain_bindings(ref):
            arg = b.arguments.get(parameter)
            if b.validator != validator or not isinstance(arg, LiteralArg):
                continue
            if isinstance(arg.literal, ScalarLiteral) and arg.literal.base_type == "integer":
                found.append(arg.literal.value)
        return min(found) if found else None

    def _presentation(self, ref: AnyTypeRef | None) -> dict[str, Any] | None:
        if not isinstance(ref, TypeRef):
            return None
        found = self.d.effective_interface(ref.type_uuid)
        interface = self.interfaces.get(found[0]) if found else None
        if interface is None:
            return None
        return {
            "interface": interface.name,
            "picture": interface.picture,
            "decimal_point": interface.decimal_point,
            "group_mark": interface.group_mark,
            "blank": interface.blank,
            "parse_lenient": interface.parse_lenient,
        }

    # --- rules --------------------------------------------------------------

    def _chain_bindings(self, ref: AnyTypeRef | None) -> list[Binding]:
        if not isinstance(ref, TypeRef):
            return []
        return [b for uuid in reversed(self.d.type_chain(ref.type_uuid)) for b in self.d.types[uuid].validators]

    def _type_rules(self, ref: AnyTypeRef | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Inherited rules first, root of the chain to the Type itself.
        Precision and scale are carried by `numeric` and not repeated."""
        check: list[dict[str, Any]] = []
        application: list[dict[str, Any]] = []
        if not isinstance(ref, TypeRef):
            return check, application
        for uuid in reversed(self.d.type_chain(ref.type_uuid)):
            owner = self.d.types[uuid]
            for b in owner.validators:
                if b.validator in (MAX_PRECISION, MAX_SCALE):
                    continue
                self._sort(self._rule(b, {}, owner.name), check, application)
        return check, application

    def _entity_rules(self, entity: Entity) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        check: list[dict[str, Any]] = []
        application: list[dict[str, Any]] = []
        by_uuid = {s.uuid: s for s in self.d.effective_slots(entity.uuid)}
        for uuid in reversed(self.d.ancestors_of(entity.uuid)):
            owner = self.d.entities[uuid]
            for b in owner.validators:
                names = {
                    k: by_uuid[a.slot].slot_name
                    for k, a in b.arguments.items()
                    if isinstance(a, SlotArg) and a.slot in by_uuid
                }
                self._sort(self._rule(b, names, owner.name), check, application)
        return check, application

    def _schema_rule(self, b: SchemaBinding) -> dict[str, Any]:
        """Cross-entity rules are always the application's (spec §9.4), so
        there is nothing to sort. Paths are written as relationship names."""
        anchor = self.d.entities[b.anchor] if b.anchor else None
        if anchor is None:
            raise ExportError("a Schema rule has no anchor")
        paths: dict[str, str] = {}
        for name, arg in b.arguments.items():
            if isinstance(arg, PathArg):
                resolved = self.d.resolve_path(anchor.uuid, arg.path)
                if resolved is None:
                    raise ExportError(f"a path on {anchor.name} does not resolve")
                paths[name] = ".".join(s.slot_name for s in resolved)
        rule = self._rule(b, paths, None)
        rule.pop("from")
        literal = rule.pop("arguments", None)
        return {
            "rule": rule["rule"],
            "anchor": anchor.name,
            "paths": paths,
            **({"arguments": literal} if literal else {}),
            "expression": rule["expression"],
            "message": rule["message"],
            "reason": "spans tables",
        }

    @staticmethod
    def _sort(rule: dict[str, Any], check: list[dict[str, Any]], application: list[dict[str, Any]]) -> None:
        if _CLOCK.search(rule["expression"]):
            application.append({**rule, "reason": "not deterministic"})
        else:
            check.append(rule)

    def _rule(self, b: Binding, names: dict[str, str], owner: str | None) -> dict[str, Any]:
        """One binding, resolved: its Validator's name, the literal arguments,
        the expanded expression with everything substituted, and the message
        the binding shows."""
        validator = self._validator(b.validator) if b.validator else None
        if validator is None:
            raise ExportError(f"a rule on {owner} names a Validator that does not exist")
        literals = {k: a.literal for k, a in b.arguments.items() if isinstance(a, LiteralArg)}
        substitutions = {**{k: _source(v) for k, v in literals.items()}, **names}
        expression = self._expand(validator, substitutions, 0)
        message = (b.message or validator.message).format_map(_Keep({k: _plain(v) for k, v in literals.items()}))
        return {
            "rule": validator.name,
            **({"arguments": {k: encode(v) for k, v in literals.items()}} if literals else {}),
            "expression": expression,
            "message": message,
            "from": owner,
        }

    def _validator(self, uuid: UUID) -> Validator | None:
        return self.library.get(uuid) or self.validators.get(uuid)

    def _expand(self, validator: Validator, substitutions: dict[str, str], depth: int) -> str:
        """A leaf is its expression with arguments substituted. A composite is
        its operands' expansions joined by the operators, each operand in
        parentheses so precedence never depends on the reader's rules."""
        if depth > MAX_DEPTH:
            raise ExportError(f"{validator.name} does not resolve")
        if not validator.is_composite:
            # an unset argument would leave its name in the expression; the
            # model check reports it as MOD108, which blocks before this runs
            return _substitute(validator.expression, substitutions)

        # the parser reads identifiers and a stored operand is a UUID, which may
        # begin with a digit, so each one stands in as a placeholder name
        operands: dict[str, UUID] = {}

        def placeholder(match: re.Match[str]) -> str:
            name = f"_operand{len(operands)}"
            operands[name] = UUID(match.group(0))
            return name

        source = UUID_PATTERN.sub(placeholder, validator.expression)

        def render(node: object, top: bool) -> str:
            if isinstance(node, Operand):
                uuid = operands.get(node.token)
                operand = self._validator(uuid) if uuid else None
                if operand is None:
                    raise ExportError(f"{validator.name} names an operand that does not exist")
                return f"({self._expand(operand, substitutions, depth + 1)})"
            if isinstance(node, Not):
                # `not` binds looser than `!=`, so it is bracketed too
                text = f"not {render(node.operand, False)}"
                return text if top else f"({text})"
            if isinstance(node, BinOp):
                text = f"{render(node.left, False)} {_COMPOSITE_OPS[node.op]} {render(node.right, False)}"
                return text if top else f"({text})"
            raise ExportError(f"{validator.name} does not parse")

        try:
            return render(parse(source), True)
        except ParseError as error:
            raise ExportError(f"{validator.name} does not parse: {error.message}") from error

    # --- names and messages -------------------------------------------------

    def _context_path(self, context: UUID | None) -> str:
        return "/".join(self.d.contexts[c].name for c in reversed(self.d.ancestry(context)) if c in self.d.contexts)

    def _warning(self, finding: Diagnostic) -> dict[str, Any]:
        names = {item.uuid: item.name for item in self.model.index().values()}
        names.update({v.uuid: v.name for v in (self.library.by_name(n) for n in self.library.names) if v})
        return {
            "code": finding.code,
            "item": names.get(finding.subject.item_uuid, ""),
            "message": render(definition(finding.code).template, finding.args, names),
        }


class _Keep(dict):
    """`str.format_map` that leaves an unknown placeholder as written."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _plain(literal: Literal) -> str:
    """A literal as a person reads it in a message."""
    if isinstance(literal, ListLiteral):
        return ", ".join(str(v) for v in literal.values)
    return str(literal.value)


def _scalar_source(base_type: str, value: Any) -> str:
    if base_type == "boolean":
        return "True" if value else "False"
    if base_type in ("integer", "real"):
        return repr(value)
    if base_type == "decimal":
        # exact as written: a fraction-shaped literal is read as decimal, never
        # as binary floating point (signature table §4)
        return format(Decimal(value), "f")
    # strings, and temporal values written as their ISO text
    return json.dumps(encode(ScalarLiteral(base_type, value))[base_type], ensure_ascii=False)


def _source(literal: Literal) -> str:
    """A literal as expression source text."""
    if isinstance(literal, ListLiteral):
        return "[" + ", ".join(_scalar_source(literal.element_type, v) for v in literal.values) + "]"
    return _scalar_source(literal.base_type, literal.value)


def _substitute(expression: str, substitutions: dict[str, str]) -> str:
    """Replace parameter names with their arguments, by token rather than by
    text, so a name inside a string literal is left alone. A name followed by
    `(` is a function call, not a parameter."""
    if not substitutions:
        return expression
    starts = [0]
    for line in expression.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(expression).readline) if t.type != tokenize.NL]
    edits: list[tuple[int, int, str]] = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string not in substitutions:
            continue
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        if following is not None and following.type == tokenize.OP and following.string == "(":
            continue
        start = starts[tok.start[0] - 1] + tok.start[1]
        end = starts[tok.end[0] - 1] + tok.end[1]
        edits.append((start, end, substitutions[tok.string]))
    for start, end, text in reversed(edits):
        expression = expression[:start] + text + expression[end:]
    return expression
