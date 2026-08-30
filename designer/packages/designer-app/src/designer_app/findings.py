"""The model check, arranged for reading.

The status line can say "1 warning, 2 notes" and stop there; a list has to say
which, about what, and in words. Turning a report into rows is decided here
rather than in the window, so the ordering, the wording and the navigation
target are testable without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from designer_model import Model, Report
from designer_model.codes import blocks_export, definition
from designer_model.diagnostics import Severity
from designer_model.ids import short
from designer_model.stdlib import Library

from .rows import label_of

MARKERS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INCOMPLETE: "unfinished",
    Severity.INFO: "note",
}

# The order they are worth reading in, which is not the order they are found.
ORDER = [Severity.ERROR, Severity.WARNING, Severity.INCOMPLETE, Severity.INFO]

# What the View menu offers, least noisy first. The default is `warning`
# because a model under construction is *full* of unfinished items and orphans
# — every type is unreferenced until something references it — and a list that
# is mostly noise is a list nobody reads.
LEVELS = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "unfinished": Severity.INCOMPLETE,
    "everything": Severity.INFO,
}
LEVEL_LABELS = {
    "error": "Errors only",
    "warning": "Warnings and errors",
    "unfinished": "Unfinished items too",
    "everything": "Everything, including notes",
}
DEFAULT_LEVEL = "warning"


def at_least(rows: list[FindingRow], level: str) -> list[FindingRow]:
    """The rows at or above a severity."""
    ceiling = ORDER.index(LEVELS.get(level, Severity.INFO))
    return [row for row in rows if ORDER.index(row.severity) <= ceiling]


@dataclass(frozen=True, slots=True)
class FindingRow:
    id: str
    severity: Severity
    marker: str
    code: str
    where: str
    message: str
    item: UUID
    kind: str
    field: str
    blocks_export: bool

    @property
    def cells(self) -> tuple[str, ...]:
        return (self.marker, self.code, self.where, self.message)


def _names(model: Model, library: Library | None) -> dict[UUID, str]:
    known = {uuid: item.name for uuid, item in model.index().items()}
    if library is not None:
        known.update({library.by_name(n).uuid: n for n in library.names})
    return known


def summarise(model: Model, report: Report, library: Library | None = None) -> list[FindingRow]:
    """Every finding, worst first."""
    from designer_model.diagnostics import render

    known = _names(model, library)
    index = model.index()
    out: list[FindingRow] = []
    for finding in report.findings:
        code = definition(finding.code)
        item = index.get(finding.subject.item_uuid)
        field = finding.subject.path[0].field if finding.subject.path else ""
        where = f"{type(item).__name__} {label_of(item)}" if item else f"<gone {short(finding.subject.item_uuid)}>"
        if field:
            where += f" · {field}"
        out.append(
            FindingRow(
                id=f"{finding.code}:{finding.subject}",
                severity=code.severity,
                marker=MARKERS[code.severity],
                code=finding.code,
                where=where,
                message=render(code.template, finding.args, known),
                item=finding.subject.item_uuid,
                kind=type(item).__name__ if item else "",
                field=field,
                blocks_export=blocks_export(finding.code),
            )
        )
    out.sort(key=lambda row: (ORDER.index(row.severity), row.code, row.where))
    return out


def headline(report: Report, level: str = DEFAULT_LEVEL) -> str:
    """What the status line says.

    Named counts rather than a total: "3 findings" hides whether any of them
    stops an export.

    Whatever the level filters out is counted, and anything that would block an
    export is named however low the level — hiding those would let a model
    reach an export with a fault nobody was shown.
    """
    counts = report.counts()
    ceiling = ORDER.index(LEVELS.get(level, Severity.INFO))
    shown = [severity for severity in ORDER[: ceiling + 1] if counts[severity]]
    hidden = sum(counts[severity] for severity in ORDER[ceiling + 1 :])

    parts = [f"{counts[s]} {MARKERS[s]}{'s' if counts[s] > 1 else ''}" for s in shown]
    if not parts:
        parts = ["no findings" if not hidden else "nothing at this level"]
    tail = f", {hidden} hidden" if hidden else ""

    blocking = len(report.export_blockers)
    if blocking:
        tail += f" ({blocking} would block an export)"
    return ", ".join(parts) + tail
