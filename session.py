"""The session.

Everything the interface needs from the model, with no interface in it: the
document, the undo stack, the dirty flag, autosave, and the findings. Written
here rather than in the app package so it can be driven by a test, a
command-line tool, or a different front end.

The one thing it deliberately does not do is schedule. Autosave is debounced by
whoever owns an event loop; this object only says whether a write is owed and
performs it when asked.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from . import persistence
from .check import Checker, Report
from .commands import Command, CommandStack
from .deletion import DeletePlan, plan_delete
from .diagnostics import Scope
from .model import Model
from .stdlib import Library, standard_library

AUTOSAVE_NAME = "autosave.json"
BACKUP_SUFFIX = ".bak"


@dataclass(frozen=True, slots=True)
class AutosaveRecord:
    """What a recovery file holds: the model, where it belongs, and when."""

    model: Model
    path: Path | None
    saved_at: dt.datetime


class Session:
    def __init__(
        self,
        model: Model | None = None,
        path: Path | None = None,
        library: Library | None = None,
        undo_limit: int = 100,
    ) -> None:
        self.model = model if model is not None else Model()
        self.path = path
        self.library = library if library is not None else standard_library()
        self.stack = CommandStack(self.model, limit=undo_limit)
        self._dirty = False
        self._autosave_owed = False
        self._report: Report | None = None

    # --- opening and saving -------------------------------------------------

    @classmethod
    def open(cls, path: str | Path, **kwargs) -> Session:
        path = Path(path)
        return cls(persistence.load(path), path, **kwargs)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def save(self, path: str | Path | None = None) -> Path:
        """Save, keeping one generation of backup.

        The backup is what covers the two edges undo does not: a delete that
        happened before a crash, and a delete more than `undo_limit` actions
        ago.
        """
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("no path: pass one, or open a file first")
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + BACKUP_SUFFIX))
        persistence.save(self.model, target)
        self.path = target
        self._dirty = False
        self._autosave_owed = False
        return target

    # --- editing ------------------------------------------------------------

    def execute(self, command: Command) -> Report:
        self.stack.execute(command)
        return self._after_change(command.touches())

    def undo(self) -> Report | None:
        command = self.stack.undo()
        if command is None:
            return None
        return self._after_change(command.touches())

    def redo(self) -> Report | None:
        command = self.stack.redo()
        if command is None:
            return None
        return self._after_change(command.touches())

    def _after_change(self, touched: set[UUID]) -> Report:
        self._dirty = True
        self._autosave_owed = True
        return self.recheck(touched)

    # --- deleting -----------------------------------------------------------

    def plan_delete(self, target: UUID) -> DeletePlan:
        """What a delete would do. Show this before doing it; the same plan
        carries it out, so the two cannot disagree."""
        return plan_delete(self.model, target)

    def apply(self, plan: DeletePlan) -> Report:
        return self.execute(plan.command)

    # --- checking -----------------------------------------------------------

    def recheck(self, touched: set[UUID] | None = None) -> Report:
        """Re-check after an edit.

        Item and context rules only. Model-scope rules — orphans, entities in no
        schema — are the deferrable ones: none is urgent while typing, and
        running them on every keystroke is what makes an incremental check
        pointless.
        """
        checker = Checker(self.model, self.library)
        self._report = checker.run(frozenset({Scope.ITEM, Scope.CONTEXT})) if touched is not None else checker.run()
        return self._report

    @property
    def report(self) -> Report:
        if self._report is None:
            self._report = Checker(self.model, self.library).run()
        return self._report

    def full_check(self) -> Report:
        """Every rule, including model scope. On demand, and before export."""
        self._report = Checker(self.model, self.library).run()
        return self._report

    # --- autosave -----------------------------------------------------------

    @property
    def autosave_owed(self) -> bool:
        return self._autosave_owed

    def write_autosave(self, directory: str | Path) -> Path:
        """Write the recovery file atomically.

        Temp file then `os.replace`, which is atomic on POSIX and on Windows
        where a plain write is not. A crash mid-write would otherwise leave a
        truncated recovery file — the one file that must never be corrupt.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / AUTOSAVE_NAME
        payload = {
            "path": str(self.path) if self.path else None,
            "saved_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "model": persistence.dump(self.model),
        }
        scratch = target.with_suffix(".tmp")
        scratch.write_text(json.dumps(payload, indent=2) + "\n")
        scratch.replace(target)
        self._autosave_owed = False
        return target

    def clear_autosave(self, directory: str | Path) -> None:
        """Remove the recovery file. Its presence at startup is what says the
        last session did not end cleanly, so it goes on a clean exit and on a
        successful save."""
        (Path(directory) / AUTOSAVE_NAME).unlink(missing_ok=True)


def read_autosave(directory: str | Path) -> AutosaveRecord | None:
    path = Path(directory) / AUTOSAVE_NAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        model = persistence.load(payload["model"])
    except (OSError, ValueError, KeyError, persistence.DocumentError):
        return None  # a damaged recovery file must not prevent startup
    saved_at = dt.datetime.fromisoformat(payload["saved_at"].replace("Z", "+00:00"))
    belongs_to = payload.get("path")
    return AutosaveRecord(model, Path(belongs_to) if belongs_to else None, saved_at)
