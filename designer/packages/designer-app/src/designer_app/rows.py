"""What goes in each column.

No tkinter. Turning a model into rows — the trees, the filtering, the styling
tags — is the part most likely to be wrong and the part a display cannot help
you check, so it lives here where a test can reach it. The widgets are thin
adapters over this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from designer_model import Deriver, Model
from designer_model.expressions.types import BASE_TYPES
from designer_model.model import TypeRef
from designer_model.stdlib import Library

BASE_PREFIX = "base:"


@dataclass(frozen=True, slots=True)
class Row:
    """One line in a column. `parent` is empty for a root."""

    id: str
    label: str
    kind: str
    parent: str = ""
    tags: tuple[str, ...] = ()

    @property
    def uuid(self) -> UUID | None:
        return None if self.id.startswith(BASE_PREFIX) else UUID(self.id)


@dataclass
class ColumnData:
    kind: str
    rows: list[Row] = field(default_factory=list)

    def ids(self) -> list[str]:
        return [r.id for r in self.rows]

    def labels(self) -> list[str]:
        return [r.label for r in self.rows]


def default_context(model: Model) -> UUID | None:
    """The context to start in.

    Every item belongs to a context, so "no context" is not a state the
    application should sit in: with nothing active, the columns show items from
    every branch at once, including ones that are invisible to each other. The
    first root — the one with no parent — is where a model starts.
    """
    roots = sorted((c for c in model.contexts if c.parent is None), key=lambda c: c.name.lower())
    return roots[0].uuid if roots else None


def context_path(model: Model, context: UUID | None) -> list[tuple[UUID, str]]:
    """A context and its ancestors, root first.

    Shared by the breadcrumb and the editor so the two cannot disagree about
    where an item sits.
    """
    by_uuid = {c.uuid: c for c in model.contexts}
    out: list[tuple[UUID, str]] = []
    current, guard = context, 0
    while current in by_uuid and guard < 64:
        item = by_uuid[current]
        out.append((item.uuid, label_of(item)))
        current, guard = item.parent, guard + 1
    return list(reversed(out))


def context_label(model: Model, context: UUID | None, separator: str = " \u203a ") -> str:
    return separator.join(name for _, name in context_path(model, context)) or "(none)"


FLOOR_CHARS = 6
"""The narrowest a column may ever be: a floor under the content-derived width
below, not a width in its own right."""


def preferred_width(widths: list[int], em: int, columns: int = 7, screen: int = 1024) -> int:
    """How wide a column should be, from what is actually in it.

    Three quarters of the widest row: the longest name is usually an outlier,
    and sizing to the worst case gives columns that will not fit together.

    Both the starting width *and* the minimum. An earlier version made this a
    preferred width with a flat ten-character floor under it, which was wrong
    in both directions: the floor swallowed the calculation for every column of
    short names, and the ceiling was fixed without reference to how many
    columns there are, so adding a seventh pushed the total past the screen it
    was meant to fit.

    The ceiling is derived instead, so every column at its widest still fits.
    `screen` defaults to a small display for callers that have no window to ask;
    the interface passes the real width, because the window starts maximised and
    a constant would cap the columns on every larger screen.
    """
    widest = max(widths, default=0)
    ceiling = max(FLOOR_CHARS * em, screen // max(columns, 1) - em)
    return max(minimum_width(em), min(int(widest * 0.75), ceiling))


def minimum_width(em: int, floor_chars: int = FLOOR_CHARS) -> int:
    """The absolute floor, in the interface font rather than in pixels, so it
    follows font size and display scaling."""
    return floor_chars * em


def label_of(item) -> str:
    """A blank name shows as a placeholder rather than an empty line, because a
    new item is created empty and has to be selectable before it is named."""
    return item.name or f"<unnamed {type(item).__name__}>"


def _visible(deriver: Deriver, items, context: UUID | None):
    if context is None:
        return list(items)
    ancestry = set(deriver.ancestry(context))
    return [i for i in items if i.context in ancestry]


def _matches(row_label: str, text: str) -> bool:
    return text.lower() in row_label.lower() if text else True


def _by_label(rows: list[Row], descending: bool = False) -> list[Row]:
    return sorted(rows, key=lambda r: r.label.lower(), reverse=descending)


def contexts(model: Model, filter_text: str = "", descending: bool = False) -> ColumnData:
    """The context tree. Never filtered by the active context — it *is* the
    active context's navigator."""
    rows = [
        Row(
            str(c.uuid),
            label_of(c),
            "Context",
            str(c.parent) if c.parent else "",
            () if c.name else ("unnamed",),
        )
        for c in model.contexts
    ]
    return ColumnData("Context", _keep_tree(rows, filter_text, descending))


def schemas(model: Model, context: UUID | None, filter_text: str = "", descending: bool = False) -> ColumnData:
    deriver = Deriver(model)
    rows = [
        Row(str(s.uuid), label_of(s), "Schema", "", () if s.name else ("unnamed",))
        for s in _visible(deriver, model.schemas, context)
        if _matches(label_of(s), filter_text)
    ]
    return ColumnData("Schema", _by_label(rows, descending))


def entities(model: Model, context: UUID | None, filter_text: str = "", descending: bool = False) -> ColumnData:
    """An extension tree, with abstract entities styled apart since they never
    materialise. A parent outside the visible set is dropped, so the row
    reparents to the root rather than vanishing."""
    deriver = Deriver(model)
    visible = _visible(deriver, model.entities, context)
    ids = {e.uuid for e in visible}
    rows = []
    for entity in visible:
        tags = []
        if entity.abstract:
            tags.append("abstract")
        if not entity.name:
            tags.append("unnamed")
        parent = str(entity.extends) if entity.extends in ids else ""
        rows.append(Row(str(entity.uuid), label_of(entity), "Entity", parent, tuple(tags)))
    return ColumnData("Entity", _keep_tree(rows, filter_text, descending))


def properties(model: Model, context: UUID | None, filter_text: str = "", descending: bool = False) -> ColumnData:
    deriver = Deriver(model)
    rows = [
        Row(str(p.uuid), label_of(p), "Property", "", () if p.name else ("unnamed",))
        for p in _visible(deriver, model.properties, context)
        if _matches(label_of(p), filter_text)
    ]
    return ColumnData("Property", _by_label(rows, descending))


def interfaces(model: Model, context: UUID | None, filter_text: str = "", descending: bool = False) -> ColumnData:
    """The presentations. Flat: an Interface has no parent and no chain."""
    deriver = Deriver(model)
    rows = []
    for item in _visible(deriver, model.interfaces, context):
        tags = [] if item.name else ["unnamed"]
        if not item.base_type or not item.picture.strip():
            tags.append("incomplete")
        rows.append(Row(str(item.uuid), label_of(item), "Interface", "", tuple(tags)))
    return ColumnData("Interface", _by_label([r for r in rows if _matches(r.label, filter_text)], descending))


def types(model: Model, context: UUID | None, filter_text: str = "", descending: bool = False) -> ColumnData:
    """A forest rooted at the BaseTypes, which are global and read-only.

    A Type with no parent yet has nowhere to hang, so it sits at the root — an
    incomplete item must still be reachable.
    """
    deriver = Deriver(model)
    rows = [Row(f"{BASE_PREFIX}{name}", name, "BaseType", "", ("builtin",)) for name in BASE_TYPES]
    visible = _visible(deriver, model.types, context)
    ids = {t.uuid for t in visible}
    for item in visible:
        parent = ""
        if isinstance(item.parent, TypeRef):
            if item.parent.type_uuid in ids:
                parent = str(item.parent.type_uuid)
        elif item.parent is not None:
            parent = f"{BASE_PREFIX}{item.parent.base_type}"
        tags = () if item.name else ("unnamed",)
        if item.parent is None:
            tags = (*tags, "incomplete")
        rows.append(Row(str(item.uuid), label_of(item), "Type", parent, tags))
    return ColumnData("Type", _keep_tree(rows, filter_text, descending))


def validators(
    model: Model,
    context: UUID | None,
    filter_text: str = "",
    library: Library | None = None,
    show_builtins: bool = False,
    descending: bool = False,
) -> ColumnData:
    """Authored validators, and optionally the built-ins.

    Built-ins default to hidden once a model has validators of its own: forty of
    them swamping a user's five makes the column useless.
    """
    deriver = Deriver(model)
    rows = [
        Row(str(v.uuid), label_of(v), "Validator", "", () if v.name else ("unnamed",))
        for v in _visible(deriver, model.validators, context)
    ]
    if show_builtins and library is not None:
        rows += [Row(str(library.by_name(n).uuid), n, "Validator", "", ("builtin",)) for n in sorted(library.names)]
    rows = [r for r in rows if _matches(r.label, filter_text)]
    # built-ins stay after the authored ones whichever way the sort runs: that
    # is a grouping, not a sort key, and reversing it would bury the model's
    # own validators under forty library entries
    authored = _by_label([r for r in rows if "builtin" not in r.tags], descending)
    built_in = _by_label([r for r in rows if "builtin" in r.tags], descending)
    return ColumnData("Validator", authored + built_in)


def _keep_tree(rows: list[Row], filter_text: str, descending: bool = False) -> list[Row]:
    """Filter a tree without orphaning matches.

    A row survives if it matches or has a surviving descendant; an ancestor kept
    only to hold a match is tagged so the interface can grey it.
    """
    if not filter_text:
        return _in_tree_order(rows, descending)
    by_id = {r.id: r for r in rows}
    keep: set[str] = set()
    for row in rows:
        if _matches(row.label, filter_text):
            keep.add(row.id)
            parent = row.parent
            while parent and parent in by_id and parent not in keep:
                keep.add(parent)
                parent = by_id[parent].parent
    matched = {r.id for r in rows if _matches(r.label, filter_text)}
    kept = [
        Row(r.id, r.label, r.kind, r.parent, (*r.tags, "context-only") if r.id not in matched else r.tags)
        for r in rows
        if r.id in keep
    ]
    return _in_tree_order(kept, descending)


def _in_tree_order(rows: list[Row], descending: bool = False) -> list[Row]:
    """Parents before children, siblings alphabetical, so a tree widget can
    insert rows in one pass without forward references.

    Reversing sorts the siblings at each level; it does not turn the tree
    upside down, which would put children before their parents and break the
    single-pass insert.
    """
    children: dict[str, list[Row]] = {}
    for row in rows:
        children.setdefault(row.parent, []).append(row)
    present = {r.id for r in rows}
    ordered: list[Row] = []

    def walk(parent: str) -> None:
        for row in _by_label(children.get(parent, []), descending):
            ordered.append(row)
            walk(row.id)

    walk("")
    for row in rows:  # a row whose parent was filtered out still has to appear
        if row.id not in {r.id for r in ordered} and row.parent not in present:
            ordered.append(row)
    return ordered
