"""The test bench, decided without a window.

Which Type a request means and how a trial is laid out as rows are settled
here and tested for real; the window in `dialogs.py` draws them and polls the
job. The judging itself is `designer_model.bench`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from designer_model import Model
from designer_model.bench import FAIL, PASS, Trial, Verdict
from designer_model.model import Property, Type, TypeRef

from .selection import Selection

MARKS = {PASS: "passes", FAIL: "fails"}
"""What the Result column says. Anything else is shown as the bench says it."""


def type_of(model: Model, uuid: UUID | None) -> UUID | None:
    """The Type an item means: itself, or a Property's. A Property typed by a
    base type has no rules to try, so it means nothing here."""
    item = model.get(uuid)
    if isinstance(item, Type):
        return item.uuid
    if isinstance(item, Property) and isinstance(item.type, TypeRef):
        return item.type.type_uuid
    return None


def target(model: Model, selection: Selection) -> UUID | None:
    """What Model ▸ Try a value… means: the item in the editor if it has a
    Type, otherwise the selected Type, otherwise the selected Property's."""
    for uuid in (selection.active_item(), selection.type, selection.property):
        found = type_of(model, uuid)
        if found is not None:
            return found
    return None


@dataclass(frozen=True, slots=True)
class Row:
    id: str
    parent: str
    values: tuple[str, str, str, str]
    """Rule, From, Result, Why."""
    tag: str
    """pass | fail | unanswered — what colours it."""


def rows(trial: Trial) -> list[Row]:
    """Every verdict as a row, a composite's operands nested under it."""
    out: list[Row] = []

    def add(verdict: Verdict, parent: str, path: str) -> None:
        tag = {PASS: "pass", FAIL: "fail"}.get(verdict.outcome, "unanswered")
        result = MARKS.get(verdict.outcome, verdict.outcome)
        out.append(Row(path, parent, (verdict.rule, verdict.origin, result, verdict.detail), tag))
        for position, operand in enumerate(verdict.operands):
            add(operand, path, f"{path}.{position}")

    for position, verdict in enumerate(trial.verdicts):
        add(verdict, "", str(position))
    return out
