"""What the editor shows for a selected item.

No tkinter. A form is described here as data — which fields, what kind, what
choices, what is wrong with them — and rendered by a widget elsewhere. That
split is what makes the interesting parts testable: which Types may be a
parent, which choices would create a cycle, where a finding attaches.

Every item shares a header (name, description, and the read-only identity), and
each kind adds its own fields. The forms are generated from this rather than
hand-built per kind, so a new field appears in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from designer_model import Deriver, Model, Report
from designer_model.codes import definition
from designer_model.diagnostics import Severity
from designer_model.expressions import tokens
from designer_model.expressions.types import BASE_TYPES
from designer_model.membership import addable
from designer_model.model import BaseTypeRef, Context, Entity, Property, Schema, Type, TypeRef, Validator
from designer_model.stdlib import Library

from .rows import BASE_PREFIX, context_label, label_of

# How the interface turns a widget value back into something the model holds.
PLAIN = "plain"  # a string, straight through
BOOL = "bool"
COMPOSITE = "composite"  # names on screen, identities in the file
ITEM_REF = "item_ref"  # a UUID or None
TYPE_REF = "type_ref"  # BaseTypeRef, TypeRef, or None

NONE_CHOICE = "\u2014 none \u2014"


@dataclass(frozen=True, slots=True)
class Choice:
    id: str | None
    label: str


@dataclass(frozen=True, slots=True)
class TableRow:
    """One line of an editable list."""

    id: str
    cells: tuple[str, ...]
    tags: tuple[str, ...] = ()
    removable: bool = True


@dataclass(frozen=True, slots=True)
class Action:
    """A button beside a table.

    `needs_row` marks the ones that act on a selection, so the interface can
    disable rather than hide them — a control that comes and goes is harder to
    aim at than one that greys out.
    """

    name: str
    label: str
    enabled: bool = True
    needs_row: bool = False


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    kind: str  # readonly | text | multiline | checkbox | choice | summary
    value: object = None
    choices: tuple[Choice, ...] = ()
    converter: str = PLAIN
    note: str = ""
    findings: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[TableRow, ...] = ()
    actions: tuple[Action, ...] = ()

    @property
    def editable(self) -> bool:
        return self.kind not in {"readonly", "summary"}


@dataclass
class FormSpec:
    uuid: UUID
    kind: str
    title: str
    fields: list[Field] = field(default_factory=list)

    def by_key(self, key: str) -> Field | None:
        return next((f for f in self.fields if f.key == key), None)

    def keys(self) -> list[str]:
        return [f.key for f in self.fields]


# --- findings ---------------------------------------------------------------


def findings_by_field(report: Report | None, uuid: UUID) -> dict[str, list[str]]:
    """Group an item's findings by the field they attach to.

    The first step of a diagnostic's path names the field, which is what lets
    the form put the message beside the control that caused it rather than only
    in a list at the bottom of the window.
    """
    grouped: dict[str, list[str]] = {}
    if report is None:
        return grouped
    for finding in report.findings:
        if finding.subject.item_uuid != uuid:
            continue
        where = finding.subject.path[0].field if finding.subject.path else ""
        severity = definition(finding.code).severity
        prefix = "" if severity is Severity.INCOMPLETE else f"{severity}: "
        grouped.setdefault(where, []).append(f"{prefix}{definition(finding.code).title} ({finding.code})")
    return grouped


# --- choices ----------------------------------------------------------------


def _visible(deriver: Deriver, items, context: UUID | None):
    if context is None:
        return list(items)
    ancestry = set(deriver.ancestry(context))
    return [i for i in items if i.context in ancestry]


def context_choices(model: Model, exclude: UUID | None = None) -> tuple[Choice, ...]:
    """Contexts a parent may be set to.

    A Context may not become its own descendant, so the subtree below it is not
    offered — the alternative is letting the user build a cycle and then telling
    them off for it.
    """
    deriver = Deriver(model)
    banned = set()
    if exclude is not None:
        banned = {c.uuid for c in model.contexts if exclude in deriver.ancestry(c.uuid)}
    return (
        Choice(None, NONE_CHOICE),
        *(Choice(str(c.uuid), label_of(c)) for c in model.contexts if c.uuid not in banned),
    )


def type_choices(model: Model, context: UUID | None, exclude: UUID | None = None) -> tuple[Choice, ...]:
    """Base types first, then the Types visible here.

    A Type's own descendants are withheld for the same reason as Contexts.
    """
    deriver = Deriver(model)
    banned = set()
    if exclude is not None:
        banned = {t.uuid for t in model.types if exclude in deriver.type_chain(t.uuid)}
    choices = [Choice(None, NONE_CHOICE)]
    choices += [Choice(f"{BASE_PREFIX}{name}", name) for name in BASE_TYPES]
    choices += [
        Choice(str(t.uuid), label_of(t))
        for t in sorted(_visible(deriver, model.types, context), key=lambda t: label_of(t).lower())
        if t.uuid not in banned
    ]
    return tuple(choices)


def entity_choices(
    model: Model, context: UUID | None, exclude: UUID | None = None, concrete_only: bool = False
) -> tuple[Choice, ...]:
    deriver = Deriver(model)
    banned = set()
    if exclude is not None:
        banned = {e.uuid for e in model.entities if exclude in deriver.ancestors_of(e.uuid)}
    entities = _visible(deriver, model.entities, context)
    if concrete_only:
        entities = [e for e in entities if not e.abstract]
    return (
        Choice(None, NONE_CHOICE),
        *(
            Choice(str(e.uuid), label_of(e))
            for e in sorted(entities, key=lambda e: label_of(e).lower())
            if e.uuid not in banned
        ),
    )


def _type_ref_id(ref) -> str | None:
    if isinstance(ref, BaseTypeRef):
        return f"{BASE_PREFIX}{ref.base_type}"
    if isinstance(ref, TypeRef):
        return str(ref.type_uuid)
    return None


def parse_type_ref(choice_id: str | None):
    """A choice id back into what the model stores."""
    if not choice_id:
        return None
    if choice_id.startswith(BASE_PREFIX):
        return BaseTypeRef(choice_id[len(BASE_PREFIX) :])
    return TypeRef(UUID(choice_id))


def parse_item_ref(choice_id: str | None) -> UUID | None:
    return UUID(choice_id) if choice_id else None


# --- the forms --------------------------------------------------------------


def _header(model: Model, item, notes: dict[str, list[str]]) -> list[Field]:
    # a Context is its own place; everything else names the one it sits in
    where = item.uuid if isinstance(item, Context) else getattr(item, "context", None)
    return [
        Field(
            "name",
            "Name",
            "text",
            item.name,
            note="blank while unnamed",
            findings=tuple(notes.get("name", ())),
        ),
        Field("description", "Description", "multiline", item.description),
        Field(
            "context_path",
            "In context",
            "readonly",
            context_label(model, where),
            note="an item is moved by changing its context, not from here",
        ),
        Field("uuid", "Identity", "readonly", str(item.uuid)),
        Field("created", "Created", "readonly", item.created.isoformat()),
        Field("modified", "Modified", "readonly", item.modified.isoformat()),
    ]


def _binding_summary(model: Model, library: Library, item) -> list[str]:
    lines = []
    for binding in getattr(item, "validators", []):
        validator = library.get(binding.validator) if binding.validator else None
        if validator is None:
            validator = next((v for v in model.validators if v.uuid == binding.validator), None)
        name = label_of(validator) if validator else "<none>"
        arguments = ", ".join(f"{k}=…" for k in binding.arguments) or "no arguments"
        lines.append(f"{name} ({arguments})")
    return lines or ["none"]


def describe(
    model: Model,
    uuid: UUID,
    library: Library,
    context: UUID | None = None,
    report: Report | None = None,
) -> FormSpec | None:
    """The form for one item, or None when the uuid names nothing."""
    item = model.index().get(uuid)
    if item is None:
        return None
    notes = findings_by_field(report, uuid)
    spec = FormSpec(uuid, type(item).__name__, label_of(item), _header(model, item, notes))
    builder = {
        "Context": _context_form,
        "Type": _type_form,
        "Property": _property_form,
        "Validator": _validator_form,
        "Entity": _entity_form,
        "Schema": _schema_form,
    }[type(item).__name__]
    spec.fields += builder(model, item, library, context, notes)
    return spec


def _context_form(model, item: Context, library, context, notes) -> list[Field]:
    return [
        Field(
            "parent",
            "Parent context",
            "choice",
            str(item.parent) if item.parent else None,
            context_choices(model, exclude=item.uuid),
            ITEM_REF,
            note="its own subtree is not offered; a context cannot contain itself",
            findings=tuple(notes.get("parent", ())),
        )
    ]


def _type_form(model, item: Type, library, context, notes) -> list[Field]:
    deriver = Deriver(model)
    base = deriver.base_type_of(item.parent)
    return [
        Field(
            "parent",
            "Narrows",
            "choice",
            _type_ref_id(item.parent),
            type_choices(model, item.context, exclude=item.uuid),
            TYPE_REF,
            note=f"base type: {base}" if base else "no base type yet",
            findings=tuple(notes.get("parent", ())),
        ),
        Field(
            "validators",
            "Rules",
            "summary",
            _binding_summary(model, library, item),
            findings=tuple(notes.get("validators", ())),
        ),
    ]


def _property_form(model, item: Property, library, context, notes) -> list[Field]:
    return [
        Field(
            "type",
            "Type",
            "choice",
            _type_ref_id(item.type),
            type_choices(model, item.context),
            TYPE_REF,
            findings=tuple(notes.get("type", ())),
        )
    ]


def validator_names(model: Model, library: Library, context: UUID | None) -> dict[UUID, str]:
    """Every validator that could be named in an expression here."""
    deriver = Deriver(model)
    names = {v.uuid: v.name for v in _visible(deriver, model.validators, context) if v.name}
    names.update({library.by_name(n).uuid: n for n in library.names})
    return names


def resolver(model: Model, library: Library, context: UUID | None):
    """Name back to identity, for storing what was typed."""
    by_name = {name: uuid for uuid, name in validator_names(model, library, context).items()}
    return by_name.get


def _validator_form(model, item: Validator, library, context, notes) -> list[Field]:
    composite = item.is_composite
    # a composite stores its operands as identities and shows them by name, so
    # renaming a validator cannot break an expression that uses it
    shown = (
        tokens.to_display(item.expression, validator_names(model, library, item.context)).text
        if composite
        else item.expression
    )
    return [
        Field("kind", "Kind", "readonly", "composite" if composite else "leaf"),
        Field(
            "parameters",
            "Parameters",
            "readonly",
            ", ".join(item.parameters) or "value (implicit)",
        ),
        Field(
            "expression",
            "Expression",
            "multiline",
            shown,
            converter=COMPOSITE if composite else PLAIN,
            note=(
                "operands are stored as identities and shown by name"
                if composite
                else "one implicit argument, called value"
            ),
            findings=tuple(notes.get("expression", ())),
        ),
        Field("message", "Message when it fails", "text", item.message),
    ]


def _entity_form(model, item: Entity, library, context, notes) -> list[Field]:
    deriver = Deriver(model)
    slots = deriver.effective_slots(item.uuid)
    own = {s.uuid for s in item.slots}
    lines = []
    for slot in slots:
        origin = "" if slot.uuid in own else "  (inherited)"
        shape = "reference" if slot.is_reference else "value"
        required = "required" if slot.required else "optional"
        lines.append(f"{slot.slot_name} — {shape}, {required}{origin}")
    schemas = [label_of(s) for s in deriver.schemas_containing(item.uuid)]
    return [
        Field(
            "abstract",
            "Abstract",
            "checkbox",
            item.abstract,
            converter=BOOL,
            note="a modelling device; never becomes a table",
        ),
        Field(
            "extends",
            "Extends",
            "choice",
            str(item.extends) if item.extends else None,
            entity_choices(model, item.context, exclude=item.uuid),
            ITEM_REF,
            findings=tuple(notes.get("extends", ())),
        ),
        Field(
            "slots",
            "Slots",
            "summary",
            lines or ["none"],
            note="inherited slots are shown but edited on the entity that declares them",
            findings=tuple(notes.get("slots", ())),
        ),
        Field(
            "identity",
            "Identity",
            "summary",
            [_slot_name(slots, u) for u in deriver.effective_identity(item.uuid)] or ["none"],
        ),
        Field(
            "validators",
            "Rules",
            "summary",
            _binding_summary(model, library, item),
            findings=tuple(notes.get("validators", ())),
        ),
        Field(
            "schemas",
            "In schemas",
            "summary",
            schemas or ["none"],
            note="editing this entity affects every schema listed",
        ),
    ]


def _slot_name(slots, uuid: UUID) -> str:
    return next((s.slot_name for s in slots if s.uuid == uuid), f"<unknown {str(uuid)[:8]}>")


def _schema_form(model, item: Schema, library, context, notes) -> list[Field]:
    deriver = Deriver(model)
    dangling = deriver.unclosed_references(item)
    closure = (
        "closed"
        if not dangling
        else f"{len(dangling)} reference(s) point outside: "
        + ", ".join(f"{label_of(model.index()[m])}.{s.slot_name}" for m, s, _ in dangling)
    )
    rules = []
    for binding in item.validators:
        anchor = model.index().get(binding.anchor) if binding.anchor else None
        rules.append(
            f"{label_of(anchor) if anchor else '<no anchor>'}: {binding.message or 'rule'} [{binding.enforcement}]"
        )
    return [
        Field(
            "members",
            "Members",
            "table",
            None,
            columns=("Entity", "Context"),
            rows=tuple(
                TableRow(
                    str(uuid),
                    (
                        label_of(model.index()[uuid]),
                        context_label(model, model.index()[uuid].context),
                    ),
                )
                for uuid in item.members
                if uuid in model.index()
            ),
            actions=(
                Action("add_member", "Add\u2026", enabled=bool(addable(model, item.uuid))),
                Action("remove_member", "Remove", needs_row=True),
                Action(
                    "close_schema",
                    "Add missing referenced entities",
                    enabled=bool(dangling),
                ),
            ),
            note="nothing joins a schema by itself",
            findings=tuple(notes.get("members", ())),
        ),
        Field("closure", "Closure", "readonly", closure),
        Field(
            "validators",
            "Cross-entity rules",
            "summary",
            rules or ["none"],
            findings=tuple(notes.get("validators", ())),
        ),
    ]
