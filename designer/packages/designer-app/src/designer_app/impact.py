"""What a delete would do, in words.

The planner already returns the consequences; this arranges them. Grouped by
consequence rather than by referencing item, because "17 items reference this"
is not a decision aid and "3 schemas lose a member, 2 slots lose their target"
is.

No tkinter: the grouping, the wording and which case counts as destructive are
all decidable without a display, and none of it is checkable by looking at a
dialog.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from designer_model import Model, persistence
from designer_model.deletion import DeletePlan
from designer_model.diagnostics import ConsequenceKind, ItemRef
from designer_model.ids import short

from .rows import label_of

# One heading per consequence, in the order they are worth reading: what loses
# structure first, what merely loses a reference after.
HEADINGS: dict[ConsequenceKind, str] = {
    ConsequenceKind.EXTENSION_CLEARED: "Entities losing everything they inherit",
    ConsequenceKind.OPERAND_ORPHANED: "Expressions left naming something deleted",
    ConsequenceKind.MEMBERSHIP_REMOVED: "Schemas losing a member",
    ConsequenceKind.BINDING_REMOVED: "Rules removed",
    ConsequenceKind.ANCHOR_CLEARED: "Rules losing their anchor",
    ConsequenceKind.REFERENCE_CLEARED: "Slots losing their target",
    ConsequenceKind.PROPERTY_CLEARED: "Slots losing their property",
    ConsequenceKind.TYPE_CLEARED: "Items losing their type",
    ConsequenceKind.PARENT_CLEARED: "Items losing their parent",
}

ORDER = list(HEADINGS)

SINGULAR: dict[ConsequenceKind, str] = {
    ConsequenceKind.EXTENSION_CLEARED: "entity loses everything it inherits",
    ConsequenceKind.OPERAND_ORPHANED: "expression is left naming something deleted",
    ConsequenceKind.MEMBERSHIP_REMOVED: "schema loses a member",
    ConsequenceKind.BINDING_REMOVED: "rule is removed",
    ConsequenceKind.ANCHOR_CLEARED: "rule loses its anchor",
    ConsequenceKind.REFERENCE_CLEARED: "slot loses its target",
    ConsequenceKind.PROPERTY_CLEARED: "slot loses its property",
    ConsequenceKind.TYPE_CLEARED: "item loses its type",
    ConsequenceKind.PARENT_CLEARED: "item loses its parent",
}

PLURALS = {"Property": "properties", "Schema": "schemas", "Entity": "entities"}


def _count(word: str, many: str, number: int) -> str:
    return f"{number} {word if number == 1 else many}"


DESTRUCTIVE = {ConsequenceKind.EXTENSION_CLEARED}
"""Clearing an extension takes every inherited slot away from the descendant.
That changes an entity's shape rather than leaving a hole, which is a different
kind of loss and reads differently in the dialog."""


@dataclass(frozen=True, slots=True)
class Group:
    kind: ConsequenceKind
    heading: str
    lines: tuple[str, ...]
    destructive: bool = False


@dataclass
class Impact:
    title: str
    removing: tuple[str, ...] = ()
    groups: list[Group] = field(default_factory=list)
    subtree: str | None = None

    @property
    def destructive(self) -> bool:
        return any(group.destructive for group in self.groups)

    @property
    def affected(self) -> int:
        return sum(len(group.lines) for group in self.groups)

    def summary(self) -> str:
        if not self.groups:
            return "Nothing else refers to it."
        return "; ".join(
            _count(SINGULAR[g.kind], g.heading[0].lower() + g.heading[1:], len(g.lines)) for g in self.groups
        )


def _name(model: Model, uuid: UUID) -> str:
    item = model.index().get(uuid)
    return f"{label_of(item)} ({short(uuid)})" if item else f"<deleted {short(uuid)}>"


def _line(model: Model, consequence) -> str:
    subject = _name(model, consequence.subject.item_uuid)
    detail = []
    for key, value in consequence.args.items():
        rendered = _name(model, value.uuid) if isinstance(value, ItemRef) else str(value)
        detail.append(f"{key} {rendered}" if key != "slot" else f"slot {rendered}")
    return f"{subject}" + (f" — {', '.join(detail)}" if detail else "")


def subtree_document(model: Model, targets: tuple[UUID, ...]) -> str:
    """The part of the file that would go.

    A count is not enough for a context: the whole subtree disappears, and the
    only honest way to show that is to show it.
    """
    keep = set(targets)
    document = persistence.dump(model)
    for group in ("contexts", "validators", "types", "properties", "entities", "schemas"):
        document[group] = [row for row in document[group] if UUID(row["uuid"]) in keep]
    return json.dumps(document, indent=2)


def counts_by_kind(model: Model, targets: tuple[UUID, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    index = model.index()
    for uuid in targets:
        item = index.get(uuid)
        if item is not None:
            kind = type(item).__name__
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def summarise(model: Model, plan: DeletePlan) -> Impact:
    """Everything the dialog needs, and nothing it does not."""
    index = model.index()
    principal = index.get(plan.targets[0]) if plan.targets else None
    for uuid in plan.targets:
        item = index.get(uuid)
        if item is not None and type(item).__name__ == "Context":
            principal = item
            break

    removing = tuple(
        _count(kind.lower(), PLURALS.get(kind, kind.lower() + "s"), count)
        for kind, count in sorted(counts_by_kind(model, plan.targets).items())
    )
    impact = Impact(
        title=f"Delete {label_of(principal)}?" if principal else "Delete?",
        removing=removing,
    )

    grouped = plan.grouped()
    for kind in ORDER:
        consequences = grouped.get(kind)
        if not consequences:
            continue
        impact.groups.append(
            Group(
                kind,
                HEADINGS[kind],
                tuple(sorted(_line(model, c) for c in consequences)),
                destructive=kind in DESTRUCTIVE,
            )
        )

    if len(plan.targets) > 1:
        impact.subtree = subtree_document(model, plan.targets)
    return impact
