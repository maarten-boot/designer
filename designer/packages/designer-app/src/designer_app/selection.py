"""What a selection does to the other columns.

Only the active Context *filters*, because an item outside it is not merely
unrelated but unreachable. Everything else *highlights*.

A schema selection used to filter the Entity column to its members, on the
argument that a schema *is* its members. That was wrong in use: the column is
where members are chosen from, and hiding the non-members hides exactly the
entities somebody is looking for when adding one. Filtering on a relationship was tried and
removed: selecting a property reduced a fourteen-row Type column to the one type
it already highlighted, which tells you nothing new and takes away everything
you might compare it against or switch to. What filtering was reaching for —
finding the related row — is better served by scrolling to it.

No tkinter: this is a set calculation, and it is much easier to be sure of in a
test than by squinting at coloured rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID

from designer_model import Deriver, Model
from designer_model.model import TypeRef

COLUMN_NAMES = ("context", "type", "validator", "property", "entity", "schema")


@dataclass(frozen=True, slots=True)
class Selection:
    context: UUID | None = None
    schema: UUID | None = None
    entity: UUID | None = None
    property: UUID | None = None
    type: UUID | None = None
    validator: UUID | None = None
    active: str | None = None
    """The column chosen most recently.

    Several columns can hold a selection at once, and the editor shows one of
    them. Which one has to be *last chosen*, not last in the layout: the columns
    run from primitives to deliverable, so picking a Type after a Property would
    otherwise leave the Property in the form and nothing would appear to happen.
    """

    def active_item(self) -> UUID | None:
        """What the editor should show."""
        if self.active is not None:
            chosen = getattr(self, self.active, None)
            if chosen is not None:
                return chosen
        return next((getattr(self, name) for name in reversed(COLUMN_NAMES) if getattr(self, name)), None)


def updated(current: Selection, column: str, uuid: UUID | None) -> Selection:
    """The selection after clicking a row in one column.

    Choosing a Context clears everything else. It has to: the Context filters
    every other column, so a selection made before the change may name an item
    that is no longer visible, and a stale selection goes on highlighting things
    that are not there.

    Built with `replace` rather than by unpacking `__dict__`, which `Selection`
    does not have — it is a slots dataclass, and reaching for `__dict__` raised
    an AttributeError inside a Tk callback, where exceptions are swallowed.
    Selection silently did nothing at all.
    """
    if column == "context":
        return Selection(context=uuid, active="context" if uuid else None)
    if uuid is None and current.active == column:
        # the active column was cleared; fall back to whichever still holds one
        remaining = replace(current, **{column: None})
        fallback = next((name for name in reversed(COLUMN_NAMES) if getattr(remaining, name)), None)
        return replace(remaining, active=fallback)
    return replace(current, **{column: uuid}, active=column if uuid else current.active)


@dataclass
class Focus:
    """What each column should emphasise, given a selection.

    `uses` is what the selected item is built from; `references` is what it
    points at; `contains` is what holds it, or what it holds. They are kept
    apart so the interface can colour them differently — an entity's own
    properties and the entities it references are not the same relationship.
    """

    uses: set[UUID] = field(default_factory=set)
    references: set[UUID] = field(default_factory=set)
    contains: set[UUID] = field(default_factory=set)

    def highlighted(self) -> set[UUID]:
        return self.uses | self.references | self.contains


def focus(model: Model, selection: Selection) -> Focus:
    deriver = Deriver(model)
    result = Focus()

    if selection.schema is not None:
        schema = next((s for s in model.schemas if s.uuid == selection.schema), None)
        if schema is not None:
            result.contains |= set(schema.members)

    if selection.entity is not None:
        slots = deriver.effective_slots(selection.entity)
        result.uses |= {s.property for s in slots if s.is_value and s.property}
        result.references |= {s.target for s in slots if s.is_reference and s.target}
        result.contains |= {s.uuid for s in deriver.schemas_containing(selection.entity)}

    if selection.property is not None:
        prop = next((p for p in model.properties if p.uuid == selection.property), None)
        if prop is not None and isinstance(prop.type, TypeRef):
            result.uses.add(prop.type.type_uuid)

    if selection.type is not None:
        item = next((t for t in model.types if t.uuid == selection.type), None)
        if item is not None:
            result.uses |= {b.validator for b in item.validators if b.validator}
            if isinstance(item.parent, TypeRef):
                result.references.add(item.parent.type_uuid)

    if selection.validator is not None:
        result.contains |= {
            t.uuid for t in model.types if any(b.validator == selection.validator for b in t.validators)
        }

    return result


def reveal_target(row_ids: list[UUID], focus_result: Focus) -> UUID | None:
    """The row a column should scroll into view.

    Highlighting says which rows are related; it says nothing if the row is
    below the fold. Scrolling to it answers the question filtering was reaching
    for — where is it — without answering a question nobody asked, which is
    what is everything else.
    """
    highlighted = focus_result.highlighted()
    return next((i for i in row_ids if i in highlighted), None)


def tags_for(uuid: UUID, focus_result: Focus) -> tuple[str, ...]:
    tags = []
    if uuid in focus_result.uses:
        tags.append("uses")
    if uuid in focus_result.references:
        tags.append("references")
    if uuid in focus_result.contains:
        tags.append("contains")
    return tuple(tags)
