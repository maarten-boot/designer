"""Findings, and what they point at.

A `Diagnostic` carries a code, a locator and arguments — nothing human-facing.
Severity, title and wording belong to the code (see `codes`), so the same code
can never report as an error in one place and a warning in another, and a test
can assert a code rather than a sentence.

A `Consequence` is a different thing: it predicts what a delete *would* do,
where a diagnostic describes what *is* true. The two share `Subject` and
nothing else.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from uuid import UUID

from .ids import short


class Severity(enum.IntEnum):
    """Ordered so a sort puts what matters first."""

    ERROR = 0
    WARNING = 1
    INCOMPLETE = 2
    INFO = 3

    def __str__(self) -> str:
        return self.name.lower()


class Scope(enum.Enum):
    """How widely a rule must re-run after an edit.

    Without this an incremental check is either wrong — a rename never re-checks
    the *other* item a duplicate name conflicts with — or it rescans the whole
    model on every keystroke.
    """

    ITEM = "item"
    CONTEXT = "context"
    MODEL = "model"


class Kind(enum.StrEnum):
    CONTEXT = "Context"
    VALIDATOR = "Validator"
    TYPE = "Type"
    PROPERTY = "Property"
    ENTITY = "Entity"
    SCHEMA = "Schema"


@dataclass(frozen=True, slots=True)
class Step:
    """One hop into an item. `key` addresses a list element by UUID, never by
    index, because an index goes stale on any reorder."""

    field: str
    key: UUID | str | None = None

    def __str__(self) -> str:
        if self.key is None:
            return self.field
        return f"{self.field}[{short(self.key) if isinstance(self.key, UUID) else self.key}]"


@dataclass(frozen=True, slots=True)
class Subject:
    item_uuid: UUID
    item_kind: Kind
    path: tuple[Step, ...] = ()

    def then(self, field: str, key: UUID | str | None = None) -> Subject:
        return Subject(self.item_uuid, self.item_kind, (*self.path, Step(field, key)))

    def __str__(self) -> str:
        inside = "".join(f".{s}" for s in self.path)
        return f"{self.item_kind}:{short(self.item_uuid)}{inside}"


@dataclass(frozen=True, slots=True)
class TextSpan:
    """A character range in the **stored** expression text.

    Stored, not displayed: composite expressions hold operand UUIDs and show
    names, so the two do not share coordinates. Translating is the editor's job,
    through the token map the tokenizer emits.
    """

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ItemRef:
    """A reference to an item, rendered at display time.

    Never a name: a finding can outlive the name it was created with, and
    shadowing makes the qualified form necessary anyway.
    """

    uuid: UUID


ArgValue = str | int | ItemRef


@dataclass(frozen=True, slots=True)
class Related:
    role: str
    subject: Subject


@dataclass(frozen=True, slots=True)
class FixHint:
    """A named action the interface maps to one command.

    A name rather than a callable, so this package stays free of UI. Whatever it
    triggers must be a single command — a fix the user has to undo four times is
    worse than no button.
    """

    action: str
    label: str
    args: dict[str, ArgValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    subject: Subject
    args: dict[str, ArgValue] = field(default_factory=dict)
    span: TextSpan | None = None
    related: tuple[Related, ...] = ()
    fix: FixHint | None = None

    @property
    def key(self) -> tuple[str, Subject]:
        """Identity, so an incremental re-check can replace findings in place
        instead of rebuilding the list and losing the user's selection."""
        return (self.code, self.subject)


class ConsequenceKind(enum.StrEnum):
    """The left column of the delete impact dialog (spec §11.1)."""

    MEMBERSHIP_REMOVED = "membership_removed"
    REFERENCE_CLEARED = "reference_cleared"
    PARENT_CLEARED = "parent_cleared"
    PROPERTY_CLEARED = "property_cleared"
    TYPE_CLEARED = "type_cleared"
    EXTENSION_CLEARED = "extension_cleared"
    BINDING_REMOVED = "binding_removed"
    OPERAND_ORPHANED = "operand_orphaned"
    ANCHOR_CLEARED = "anchor_cleared"


@dataclass(frozen=True, slots=True)
class Consequence:
    kind: ConsequenceKind
    subject: Subject
    args: dict[str, ArgValue] = field(default_factory=dict)


# --- rendering --------------------------------------------------------------


def render_ref(ref: ItemRef, names: dict[UUID, str]) -> str:
    """`name (uuid)` per spec §5.3, abbreviated to eight characters."""
    name = names.get(ref.uuid)
    if name is None:
        return f"<deleted {short(ref.uuid)}>"
    if not name:
        return f"<unnamed> ({short(ref.uuid)})"
    return f"{name} ({short(ref.uuid)})"


def render(template: str, args: dict[str, ArgValue], names: dict[UUID, str]) -> str:
    resolved = {k: render_ref(v, names) if isinstance(v, ItemRef) else v for k, v in args.items()}
    try:
        return template.format(**resolved)
    except KeyError as exc:
        return f"{template} [missing argument {exc}]"
