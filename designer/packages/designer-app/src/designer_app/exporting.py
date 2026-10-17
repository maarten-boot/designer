"""File ▸ Export schema…, decided without a window.

Which Schema an export means, what the file is called, and what the person is
told when something blocks it are all settled here, so they are tested for
real; `app.py` asks for a filename and writes the text.

The export itself is `designer_model.export`. Nothing here duplicates its
rules — in particular the gate, which is the model check's own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from designer_model import ExportError, Model, export_schema
from designer_model.check import Report
from designer_model.export import dumps
from designer_model.model import Schema
from designer_model.stdlib import Library

from . import findings as findingview
from .selection import Selection


def schema_for_export(model: Model, selection: Selection) -> Schema | None:
    """The selected Schema, or the only one there is. With several and none
    selected there is no right guess, and a wrong one writes the wrong file."""
    schemas = {s.uuid: s for s in model.schemas}
    if selection.schema in schemas:
        return schemas[selection.schema]
    return model.schemas[0] if len(model.schemas) == 1 else None


def suggested_path(schema: Schema, model_path: Path | None) -> Path:
    """`<schema>.export.json`, beside the model file when there is one."""
    name = f"{schema.name or 'schema'}.export.json"
    return model_path.parent / name if model_path is not None else Path(name)


@dataclass(frozen=True, slots=True)
class Outcome:
    """Either the text to write, or the findings that stop it."""

    text: str | None = None
    blockers: list[findingview.FindingRow] = field(default_factory=list)
    headline: str = ""


def run(model: Model, schema: Schema, library: Library) -> Outcome:
    try:
        return Outcome(text=dumps(export_schema(model, schema.uuid, library)))
    except ExportError as error:
        if not error.blockers:
            # a structural refusal with no finding behind it: say it as it is
            return Outcome(headline=f"{schema.name} cannot be exported: {error}")
        rows = findingview.summarise(model, Report(error.blockers), library)
        count = len(rows)
        noun = "finding blocks" if count == 1 else "findings block"
        return Outcome(blockers=rows, headline=f"{count} {noun} the export of {schema.name}")
