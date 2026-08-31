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

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import NAMESPACE_DNS, UUID, uuid5

from designer_model import Deriver, Model, Report, pictures
from designer_model.codes import definition
from designer_model.diagnostics import Severity, render
from designer_model.expressions import tokens
from designer_model.expressions.types import BASE_TYPES
from designer_model.membership import addable
from designer_model.model import (
    BaseTypeRef,
    Context,
    Entity,
    Interface,
    Property,
    Schema,
    Slot,
    Type,
    TypeRef,
    Validator,
)
from designer_model.stdlib import Library

from .rows import BASE_PREFIX, context_label, label_of

PICTURE_HELP = {
    "integer": "0 a digit shown always, # only if needed, , grouping. e.g. #,##0",
    "decimal": "0 shown always, # if needed, . decimal, ; a negative form, % a fraction. e.g. #,##0.00;(#,##0.00)",
    "real": "as decimal. e.g. #,##0.00",
    "string": "X(n) positions, then < > or ^ to align, U or L for case. e.g. X(30)<",
    "date": "yyyy MM dd, and 'text' for literals. e.g. dd-MM-yyyy",
    "time": "HH mm ss SSS. e.g. HH:mm",
    "datetime": "yyyy MM dd HH mm ss SSS ZZ. e.g. yyyy-MM-dd'T'HH:mm:ssZZ",
    "boolean": "two labels, positive first. e.g. Yes;No",
}

BASE_TYPE_NOTES = {
    "integer": "whole numbers",
    "real": "binary floating point; may hold NaN and infinity, which no backing store accepts",
    "decimal": "exact, and never mixed with real — that is the one combination that silently destroys exactness",
    "boolean": "true or false",
    "string": "text",
    "datetime": "timezone aware, always UTC",
    "date": "no time, no zone",
    "time": "no date, no zone; comparison only",
}

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
    requires: str = ""
    """`own` for a row this item declares, `inherited` for one it does not.

    Removing an inherited slot is meaningless — it is edited on the entity that
    declares it — and overriding a slot the entity already declares is equally
    so. Disabling rather than hiding, because a control that comes and goes is
    harder to aim at than one that greys out.
    """


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
    emphasis: str = ""
    """`attention` for something true and worth noticing that is not a fault.

    A copied built-in taking precedence over the original is the point of
    copying it, so it is not a warning — but it changes what a name means, and
    that is worth seeing without hunting for it.
    """

    @property
    def editable(self) -> bool:
        return self.kind not in {"readonly", "summary"}


@dataclass
class FormSpec:
    uuid: UUID
    kind: str
    title: str
    fields: list[Field] = field(default_factory=list)
    actions: tuple[Action, ...] = ()
    read_only: bool = False
    note: str = ""

    def by_key(self, key: str) -> Field | None:
        return next((f for f in self.fields if f.key == key), None)

    def keys(self) -> list[str]:
        return [f.key for f in self.fields]


# --- findings ---------------------------------------------------------------


def findings_by_field(report: Report | None, uuid: UUID, model: Model | None = None) -> dict[str, list[str]]:
    """Group an item's findings by the field they attach to.

    The first step of a diagnostic's path names the field, which is what lets
    the form put the message beside the control that caused it rather than only
    in a list at the bottom of the window.

    The message is the diagnostic's own, rendered with its arguments. It used to
    be only the code's title — "Target has descendants (MOD404)" — which throws
    away everything that says *which* target and *what* descendants. The
    diagnostic already carries all of it; the form was simply not asking.
    """
    grouped: dict[str, list[str]] = {}
    if report is None:
        return grouped
    names = {item.uuid: label_of(item) for item in model.index().values()} if model else {}
    for finding in report.findings:
        if finding.subject.item_uuid != uuid:
            continue
        step = finding.subject.path[0] if finding.subject.path else None
        where = step.field if step else ""
        definition_ = definition(finding.code)
        severity = definition_.severity
        prefix = "" if severity is Severity.INCOMPLETE else f"{severity}: "
        message = render(definition_.template, finding.args, names)
        # which row inside the field, when the diagnostic addresses one and has
        # not already said so — several templates name the slot themselves, and
        # "…widens the inherited type — on total" reads as a stutter
        row = _row_name(model, step.key) if model and step is not None else ""
        if row and row.removeprefix(" \u2014 on ") in message:
            row = ""
        grouped.setdefault(where, []).append(f"{prefix}{message}{row} ({finding.code})")
    return grouped


def _row_name(model: Model, key: object) -> str:
    """Name the slot or binding a finding is about, when it names one by id."""
    if not isinstance(key, UUID):
        return ""
    for entity in model.entities:
        for slot in entity.slots:
            if slot.uuid == key:
                return f" \u2014 on {slot.slot_name}"
    return ""


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
            "context_path" if isinstance(item, Context) else "context",
            "In context",
            "readonly" if isinstance(item, Context) else "choice",
            context_label(model, where) if isinstance(item, Context) else (str(item.context) if item.context else None),
            () if isinstance(item, Context) else context_choices(model, exclude=None),
            PLAIN if isinstance(item, Context) else ITEM_REF,
            note=(
                "a context's own place is set by its parent, below"
                if isinstance(item, Context)
                else "move the item up or down the tree here. Moving it down may "
                "put it out of sight of something that uses it, which the model "
                "check will report"
            ),
            findings=tuple(notes.get("context", ())),
        ),
        Field("uuid", "Identity", "readonly", str(item.uuid)),
        Field("created", "Created", "readonly", item.created.isoformat()),
        Field("modified", "Modified", "readonly", item.modified.isoformat()),
    ]


def schema_describes(model: Model, library: Library, binding) -> tuple[str, ...]:
    from .bindings import schema_describes as describe

    return describe(model, library, binding)


def rules_field(model: Model, library: Library, item, notes: dict[str, list[str]], applies_to: bool) -> Field:
    """The rules attached to a Type or an Entity.

    An Entity's rules name the slot they apply to; a Type's apply to the type
    itself, so that column is only there where it means something.
    """
    from .bindings import describes

    columns = ("Rule", "Applies to", "Arguments") if applies_to else ("Rule", "Arguments")
    rows = []
    for binding in item.validators:
        name, slot, arguments = describes(model, library, item, binding)
        cells = (name, slot, arguments) if applies_to else (name, arguments)
        rows.append(TableRow(str(binding.uuid), cells))
    return Field(
        "validators",
        "Rules",
        "table",
        None,
        columns=columns,
        rows=tuple(rows),
        actions=(
            Action("add_rule", "Add\u2026"),
            Action("edit_rule", "Edit\u2026", needs_row=True),
            Action("remove_rule", "Remove", needs_row=True),
        ),
        note=(
            "each rule applies to one slot's value" if applies_to else "each rule applies to every value of this type"
        ),
        findings=tuple(notes.get("validators", ())),
    )


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
        built_in = library.get(uuid)
        if built_in is not None:
            return _builtin_form(model, built_in, library)
        return None
    notes = findings_by_field(report, uuid, model)
    spec = FormSpec(uuid, type(item).__name__, label_of(item), _header(model, item, notes))
    builder = {
        "Context": _context_form,
        "Type": _type_form,
        "Property": _property_form,
        "Validator": _validator_form,
        "Interface": _interface_form,
        "Entity": _entity_form,
        "Schema": _schema_form,
    }[type(item).__name__]
    spec.fields += builder(model, item, library, context, notes)
    return spec


BASE_TYPE_NAMESPACE = uuid5(NAMESPACE_DNS, "basetype.designer")


def base_type_uuid(name: str) -> UUID:
    """An identity for a base type, for the interface only.

    A base type has none in the document — a Type refers to one by name — but a
    form needs something to be about. Never stored.
    """
    return uuid5(BASE_TYPE_NAMESPACE, name)


def describe_base_type(model: Model, name: str) -> FormSpec | None:
    """A base type, read-only.

    The eight are fixed and built in. They have no context, are visible
    everywhere, and are the roots every Type chain ends at.
    """
    if name not in BASE_TYPES:
        return None
    deriver = Deriver(model)
    built_on = sorted(
        label_of(t) for t in model.types if isinstance(t.parent, BaseTypeRef) and t.parent.base_type == name
    )
    reaching = sorted(label_of(t) for t in model.types if deriver.base_type_of(t.parent) == name)
    return FormSpec(
        base_type_uuid(name),
        "Base type",
        name,
        [
            Field("name", "Name", "readonly", name),
            Field(
                "origin",
                "Origin",
                "readonly",
                "built in",
                note="one of the eight fixed types; global, and in no context",
            ),
            Field("notes", "Notes", "readonly", BASE_TYPE_NOTES.get(name, "")),
            Field(
                "built_on",
                "Types narrowing it directly",
                "summary",
                built_on or ["none"],
            ),
            Field(
                "reaching",
                "Types reaching it in the end",
                "summary",
                reaching or ["none"],
                note="every chain of types ends at exactly one base type",
            ),
        ],
        read_only=True,
        note=(
            "Base types cannot be edited. They are fixed, shared by every model, "
            "and the roots that every type chain ends at. To restrict one, make a "
            "Type that narrows it."
        ),
    )


def slot_property_choices(model: Model, entity: Entity) -> tuple[Choice, ...]:
    deriver = Deriver(model)
    return (
        Choice(None, NONE_CHOICE),
        *(
            Choice(str(p.uuid), label_of(p))
            for p in sorted(
                _visible(deriver, model.properties, entity.context),
                key=lambda p: label_of(p).lower(),
            )
        ),
    )


def slot_target_choices(model: Model, entity: Entity) -> tuple[Choice, ...]:
    """Every concrete entity visible from here.

    Abstract ones are left out: there is no table for a foreign key to point
    at, and that will not change by filling something in.

    An entity with **no identity yet** *is* offered, which it was not before.
    Requiring one made every newly created entity unreferenceable — and since
    an identity could not be set from the interface at all, that meant nothing
    you built could be referenced. Incomplete is the normal state of a new
    item; the model check reports the missing identity, which is its job.
    """
    deriver = Deriver(model)
    return (
        Choice(None, NONE_CHOICE),
        *(
            Choice(str(e.uuid), label_of(e))
            for e in sorted(
                _visible(deriver, model.entities, entity.context),
                key=lambda e: label_of(e).lower(),
            )
            if not e.abstract
        ),
    )


def narrowing_type_choices(model: Model, entity: Entity, inherited: Slot) -> tuple[Choice, ...]:
    """Types that narrow the inherited one.

    An override may only restrict, so offering the rest would be offering
    something that will be refused.
    """
    deriver = Deriver(model)
    current = deriver.slot_type(inherited)
    if not isinstance(current, TypeRef):
        return type_choices(model, entity.context)
    return (
        Choice(None, NONE_CHOICE),
        *(
            Choice(str(t.uuid), label_of(t))
            for t in sorted(
                _visible(deriver, model.types, entity.context),
                key=lambda t: label_of(t).lower(),
            )
            if deriver.narrows(t.uuid, current.type_uuid)
        ),
    )


def _builtin_form(model: Model, item: Validator, library: Library) -> FormSpec:
    """A built-in validator, read-only.

    Built-ins are global: no context, visible everywhere, and never written to
    the model file — only references to them are. That is why looking one up in
    the model finds nothing, and why the form has to say so rather than
    reporting the item as missing.
    """
    shown = (
        tokens.to_display(item.expression, validator_names(model, library, None)).text
        if item.is_composite
        else item.expression
    )
    deterministic = library.is_deterministic(item.uuid)
    return FormSpec(
        item.uuid,
        "Validator",
        item.name,
        [
            Field("name", "Name", "readonly", item.name),
            Field("description", "Description", "readonly", item.description),
            Field(
                "origin",
                "Origin",
                "readonly",
                "standard library",
                note=("shipped with the tool, shared by every model, and identical on every installation"),
            ),
            usage_field(item),
            Field("kind", "Kind", "readonly", "composite" if item.is_composite else "leaf"),
            Field(
                "parameters",
                "Parameters",
                "readonly",
                ", ".join(item.parameters) or "value (implicit)",
            ),
            accepts_field(model, library, item),
            Field(
                "expression",
                "Implementation",
                "readonly",
                shown,
                note=(
                    f"exposes the expression function {exposes}; the same "
                    "function can be used directly in a rule of your own"
                    if (exposes := implements(item))
                    else "how this rule is built \u2014 a model for writing your own"
                ),
            ),
            Field("message", "Message when it fails", "readonly", item.message),
            Field(
                "deterministic",
                "Deterministic",
                "readonly",
                "yes" if deterministic else "no",
                note=("" if deterministic else "reads the clock, so no check constraint can enforce it"),
            ),
            Field("uuid", "Identity", "readonly", str(item.uuid)),
            *(
                [
                    Field(
                        "shadowed",
                        "Taken precedence over by",
                        "summary",
                        [f"{label_of(v)} in {context_label(model, v.context)}" for v in shadowed],
                        emphasis="attention",
                        note="a rule naming it there gets that one instead",
                    )
                ]
                if (shadowed := shadowed_by(model, item.name))
                else []
            ),
        ],
        actions=(Action("fork_builtin", "Copy into this model\u2026"),),
        read_only=True,
        note=(
            "Built-in validators cannot be edited. Copy this one into the model "
            "to make a version you can change; rules already using the built-in "
            "keep using it."
        ),
    )


SAMPLES: dict[str, tuple] = {
    "integer": (0, 42, -1234567),
    "decimal": (Decimal("0"), Decimal("1234.5"), Decimal("-12.345")),
    "real": (0.0, 1234.5, -12.5),
    "string": ("Ada", "Ada Lovelace"),
    "boolean": (True, False),
    "date": (dt.date(2026, 8, 30),),
    "time": (dt.time(14, 22, 5),),
    "datetime": (dt.datetime(2026, 8, 30, 14, 22, 5, tzinfo=dt.UTC),),
}
"""What the preview is drawn with. Fixed values rather than anything from the
model: a picture is checked against its base type, not against a particular
column's data, and a preview that changed with the model would be a worse
answer to "what does this format do"."""


def _preview(item: Interface) -> tuple[list[str], str]:
    """A few values as this picture writes them, and what reading them back
    does. Most picture mistakes are visible the moment somebody sees one."""
    if not item.base_type or not item.picture.strip():
        return ["give it a base type and a picture"], ""
    try:
        compiled = pictures.compile_picture(item.base_type, item.picture, item.decimal_point, item.group_mark)
    except pictures.PictureError as error:
        return [f"the picture cannot be used: {error}"], ""
    samples = SAMPLES.get(item.base_type, ())
    lines = [f"{value!s:>14}  \u2192  {pictures.present(compiled, value)}" for value in samples]
    trip = pictures.check_round_trip(compiled, samples)
    return lines, "" if trip.holds else f"does not read back: {trip.why()}"


def _interface_form(model, item: Interface, library, context, notes) -> list[Field]:
    lines, problem = _preview(item)
    numeric = item.base_type in pictures.NUMERIC
    fields = [
        Field(
            "base_type",
            "Presents values of",
            "choice",
            item.base_type or None,
            (Choice(None, NONE_CHOICE), *(Choice(n, n) for n in BASE_TYPES)),
            PLAIN,
            note="an interface knows one base type; any Type over it may use this",
            findings=tuple(notes.get("base_type", ())),
        ),
        Field(
            "picture",
            "Picture",
            "text",
            item.picture,
            note=PICTURE_HELP.get(item.base_type, "choose a base type first"),
            findings=tuple(notes.get("picture", ())),
        ),
    ]
    if numeric:
        # the picture stays canonical and these say how it is written, so one
        # picture serves every region
        fields += [
            Field("decimal_point", "Decimal separator", "text", item.decimal_point),
            Field(
                "group_mark",
                "Grouping separator",
                "text",
                item.group_mark,
                note="the picture itself is always written with . and , whatever these say",
            ),
        ]
    fields += [
        Field("blank", "An absent value shows as", "text", item.blank),
        Field(
            "parse_lenient",
            "Read input leniently",
            "checkbox",
            item.parse_lenient,
            converter=BOOL,
            note="accept spacing and missing separators that cannot change the value",
        ),
        Field(
            "preview",
            "For example",
            "summary",
            lines,
            note=problem,
            emphasis="attention" if problem else "",
        ),
        Field(
            "bound_to",
            "Used by",
            "summary",
            [label_of(t) for t in model.types if any(b.interface == item.uuid for b in t.interfaces)]
            or ["nothing yet"],
        ),
    ]
    return fields


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
    faces = {i.uuid: i for i in model.interfaces}
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
        rules_field(model, library, item, notes, applies_to=False),
        _presents_with(model, item),
        Field(
            "interfaces",
            "Presentations",
            "table",
            None,
            columns=("Interface", "Picture", "Default"),
            rows=tuple(
                TableRow(
                    str(binding.uuid),
                    (
                        label_of(faces[binding.interface]) if binding.interface in faces else "(missing)",
                        faces[binding.interface].picture if binding.interface in faces else "",
                        "yes" if binding.is_default else "",
                    ),
                )
                for binding in item.interfaces
            ),
            actions=(
                Action("add_presentation", "Add\u2026"),
                Action("default_presentation", "Make default", needs_row=True),
                Action("remove_presentation", "Remove", needs_row=True),
            ),
            note="an interface for this type's base type; the default is the one used",
            findings=tuple(notes.get("interfaces", ())),
        ),
    ]


def _identity_field(model: Model, item: Entity, effective, notes) -> Field:
    """Which slots identify a row.

    Editable, which it was not: an entity with no identity cannot be
    referenced, so with no way to set one from here nothing you built could be
    pointed at. Declared once in a chain and inherited below, so a child shows
    its parent's and says where it came from.
    """
    deriver = Deriver(model)
    chosen = deriver.effective_identity(item.uuid)
    inherited = bool(chosen) and not item.identity
    origin = ""
    if inherited:
        for ancestor in deriver.ancestors_of(item.uuid):
            found = deriver.entities.get(ancestor)
            if found is not None and found.identity:
                origin = label_of(found)
                break
    by_uuid = {slot.uuid: slot for slot in effective}
    return Field(
        "identity",
        "Identity",
        "table",
        None,
        columns=("Slot", "Type"),
        rows=tuple(
            TableRow(
                str(uuid),
                (
                    by_uuid[uuid].slot_name if uuid in by_uuid else "(missing)",
                    slot_describes(model, by_uuid[uuid]) if uuid in by_uuid else "",
                ),
                tags=("inherited",) if inherited else (),
                removable=not inherited,
            )
            for uuid in chosen
        ),
        actions=(
            Action("add_identity", "Add\u2026", enabled=not inherited),
            Action("remove_identity", "Remove", needs_row=True, enabled=not inherited),
            Action("move_identity_up", "Up", needs_row=True, enabled=not inherited),
            Action("move_identity_down", "Down", needs_row=True, enabled=not inherited),
            Action("override_identity", "Declare here", enabled=inherited),
        ),
        note=(
            f"inherited from {origin}; declare one here to override it"
            if inherited
            else "the slots that identify a row, in order. An entity with none cannot be referenced"
        ),
        emphasis="attention" if inherited else "",
        findings=tuple(notes.get("identity", ())),
    )


def _indexes_field(model: Model, item: Entity, effective, notes) -> Field:
    """Indexes over this entity's slots.

    They were stored, persisted and checked, and had no control at all — the
    model check could report an index over a slot that is not there while the
    interface offered no way to have made one, or to fix it.

    Not inherited: an index is a decision about one table, and a narrowing
    entity is a different table.
    """
    by_uuid = {slot.uuid: slot for slot in effective}
    rows = []
    for position, index in enumerate(item.indexes):
        named = [by_uuid[uuid].slot_name if uuid in by_uuid else "(missing)" for uuid in index.slots]
        rows.append(
            TableRow(
                str(position),
                (", ".join(named) or "(empty)", "unique" if index.unique else ""),
            )
        )
    return Field(
        "indexes",
        "Indexes",
        "table",
        None,
        columns=("Over", "Kind"),
        rows=tuple(rows),
        actions=(
            Action("add_index", "Add\u2026"),
            Action("toggle_index_unique", "Unique", needs_row=True),
            Action("remove_index", "Remove", needs_row=True),
        ),
        note="an index over one or more of this entity's value slots",
        findings=tuple(notes.get("indexes", ())),
    )


def _default_order_field(model: Model, item: Entity, effective, notes) -> Field:
    """The order rows come back in when nothing else is asked for.

    Stored and checked and, until now, with no control — so `MOD410` could
    report an order over a slot that is no longer there while offering no way
    to remove it. The same gap indexes had.
    """
    by_uuid = {slot.uuid: slot for slot in effective}
    rows = tuple(
        TableRow(
            str(position),
            (
                by_uuid[term.slot].slot_name if term.slot in by_uuid else "(removed)",
                "ascending" if term.ascending else "descending",
            ),
            tags=() if term.slot in by_uuid else ("error",),
        )
        for position, term in enumerate(item.default_order)
    )
    return Field(
        "default_order",
        "Default order",
        "table",
        None,
        columns=("Slot", "Direction"),
        rows=rows,
        actions=(
            Action("add_order_term", "Add\u2026"),
            Action("flip_order_term", "Reverse", needs_row=True),
            Action("remove_order_term", "Remove", needs_row=True),
        ),
        note="how rows come back when nothing else is asked for; first term first",
        findings=tuple(notes.get("default_order", ())),
    )


def _presents_with(model: Model, item: Type) -> Field:
    """What this Type actually presents with, and where that came from.

    An inherited presentation that looks declared is worse than no inheritance:
    somebody edits it, and silently creates a binding where there was none.
    """
    found = Deriver(model).effective_interface(item.uuid)
    if found is None:
        return Field(
            "presents_with",
            "Presents with",
            "readonly",
            "nothing",
            note="values of this type are written however the application decides",
        )
    face_uuid, origin = found
    face = next((i for i in model.interfaces if i.uuid == face_uuid), None)
    name = label_of(face) if face else "(missing)"
    if origin == item.uuid:
        return Field("presents_with", "Presents with", "readonly", f"{name}, declared here")
    return Field(
        "presents_with",
        "Presents with",
        "readonly",
        f"{name}, inherited from {label_of(model.index()[origin])}",
        emphasis="attention",
        note="add one here to override it for this type",
    )


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


def usage(item: Validator) -> str:
    """How the rule is written where it is used.

    Not its expression. `is_country_code` is *used* as `is_country_code`; its
    expression is `regex_full_match(value, "[A-Z]{2}")`, which is how it is
    built. The two coincide for a rule like `ends_with`, whose expression is a
    call to the function of the same name, and that coincidence is exactly what
    makes showing only the expression misleading.
    """
    if not item.name:
        return "(unnamed)"
    return f"{item.name}({', '.join(item.parameters)})" if item.parameters else item.name


def implements(item: Validator) -> str | None:
    """The expression-language function a rule exposes, when it exposes one.

    Five functions return a yes or no and so can be a rule on their own:
    `contains`, `ends_with`, `starts_with`, `is_finite` and `regex_full_match`.
    The rest — `len`, `scale`, `lower` and so on — return a length or a number
    or a string, and are used inside an expression rather than being a rule.
    """
    expression = item.expression.strip()
    head, _, rest = expression.partition("(")
    if rest and head.isidentifier() and expression.endswith(")"):
        return head
    return None


def usage_field(item: Validator) -> Field:
    note = "in a composite, write just the name; its arguments come from the binding"
    if item.parameters:
        note = (
            f"supply {', '.join(item.parameters)} when binding it. "
            "In a composite, write just the name — a composite takes on the "
            "parameters of the rules it combines."
        )
    return Field("usage", "Used as", "readonly", usage(item), note=note)


def accepts_field(model: Model, library: Library, item: Validator) -> Field:
    """Which base types a validator will take.

    Read-only and derived from the expression, because a validator does not
    have *a* base type: `max_length` takes only string, `non_negative` the
    three numeric ones, `equals` all eight. A field to pick one would either
    throw that away or restate what the expression already decides.
    """
    from .bindings import accepts

    taken = accepts(model, library, item)
    if not taken:
        value = "nothing — no base type satisfies this expression"
    elif len(taken) == len(BASE_TYPES):
        value = "any base type"
    else:
        value = ", ".join(taken)
    return Field(
        "accepts",
        "Applies to values of",
        "readonly",
        value,
        note="worked out from the expression; a rule may take several base types",
    )


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


def shadowed_by(model: Model, name: str) -> list[Validator]:
    """Authored validators taking precedence over the built-in of this name."""
    return [v for v in model.validators if v.name == name]


def _validator_form(model, item: Validator, library, context, notes) -> list[Field]:
    composite = item.is_composite
    overrides = library.by_name(item.name) if item.name else None
    # a composite stores its operands as identities and shows them by name, so
    # renaming a validator cannot break an expression that uses it
    shown = (
        tokens.to_display(item.expression, validator_names(model, library, item.context)).text
        if composite
        else item.expression
    )
    fields = [
        usage_field(item),
        Field(
            "kind",
            "Kind",
            "choice",
            item.kind,
            (
                Choice("leaf", "leaf — an expression over value"),
                Choice("composite", "composite — other rules combined"),
            ),
            PLAIN,
            note=(
                "a composite combines rules by name with AND, OR, XOR, NOT and "
                "parentheses; every operand is applied to the same value"
            ),
            findings=tuple(notes.get("kind", ())),
        ),
        Field(
            "parameters",
            "Parameters",
            "readonly",
            ", ".join(item.parameters) or "value (implicit)",
        ),
        accepts_field(model, library, item),
        Field(
            "expression",
            "Expression",
            "multiline",
            shown,
            converter=COMPOSITE if composite else PLAIN,
            note=(
                "names of other rules, combined with AND, OR, XOR, NOT and "
                "parentheses \u2014 for example:  is_email OR (is_uuid AND NOT is_blank)"
                if composite
                else "one implicit argument, called value"
            ),
            findings=tuple(notes.get("expression", ())),
        ),
        Field("message", "Message when it fails", "text", item.message),
    ]
    if overrides is not None:
        fields.insert(
            0,
            Field(
                "overrides",
                "Takes precedence over",
                "readonly",
                f"the built-in {item.name}",
                emphasis="attention",
                note=(
                    "a rule naming it from here downwards gets this one. The "
                    "built-in is unchanged, and every rule already bound to it "
                    "still uses it."
                ),
            ),
        )
    return fields


def _entity_form(model, item: Entity, library, context, notes) -> list[Field]:
    deriver = Deriver(model)
    effective = deriver.effective_slots(item.uuid)
    own = {s.uuid for s in item.slots}
    # inherited slots are shown so the effective record reads in one place, but
    # they are edited on the entity that declares them
    slot_rows = tuple(
        TableRow(
            str(slot.uuid),
            (
                slot.slot_name,
                "reference" if slot.is_reference else "value",
                slot_describes(model, slot),
                "yes" if slot.required else "no",
                "" if slot.uuid in own else "inherited",
            ),
            tags=() if slot.uuid in own else ("inherited",),
            removable=slot.uuid in own,
        )
        # by position, never alphabetically: the order of slots is stored, it
        # is what the Up and Down buttons change, and it survives to the
        # generated table
        for slot in sorted(effective, key=lambda s: s.position)
    )
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
            "table",
            None,
            columns=("Name", "Kind", "Type or target", "Required", "Origin"),
            rows=slot_rows,
            actions=(
                Action("add_value_slot", "Add value\u2026"),
                Action("add_reference_slot", "Add reference\u2026"),
                Action("edit_slot", "Edit\u2026", needs_row=True, requires="own"),
                Action("override_slot", "Override\u2026", needs_row=True, requires="inherited"),
                Action("remove_slot", "Remove", needs_row=True, requires="own"),
                Action("move_slot_up", "Up", needs_row=True, requires="own"),
                Action("move_slot_down", "Down", needs_row=True, requires="own"),
            ),
            note="inherited slots are shown but edited on the entity that declares them",
            findings=tuple(notes.get("slots", ())),
        ),
        _identity_field(model, item, effective, notes),
        _indexes_field(model, item, effective, notes),
        _default_order_field(model, item, effective, notes),
        rules_field(model, library, item, notes, applies_to=True),
        Field(
            "schemas",
            "In schemas",
            "summary",
            schemas or ["none"],
            note="editing this entity affects every schema listed",
        ),
    ]


def slot_describes(model: Model, slot: Slot) -> str:
    """A slot's type or target, for a table cell."""
    from .slots import describes

    return describes(model, slot)


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

    return [
        Field(
            "members",
            "Members",
            "table",
            None,
            columns=("Entity", "Context"),
            rows=tuple(
                sorted(
                    (
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
                    key=lambda row: row.cells[0].lower(),
                )
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
            "table",
            None,
            columns=("Rule", "Anchored on", "Values", "Enforced"),
            rows=tuple(
                TableRow(str(binding.uuid), schema_describes(model, library, binding)) for binding in item.validators
            ),
            actions=(
                Action("add_schema_rule", "Add\u2026", enabled=bool(item.members)),
                Action("edit_schema_rule", "Edit\u2026", needs_row=True),
                Action("remove_schema_rule", "Remove", needs_row=True),
            ),
            note=(
                "a rule reaching across members, anchored on one of them. "
                "Always enforced in the application: a rule spanning two tables "
                "cannot be a check constraint"
            ),
            findings=tuple(notes.get("validators", ())),
        ),
    ]
