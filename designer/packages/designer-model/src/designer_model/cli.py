"""The command-line tools, installed as `designer-check` and `designer-export`.

They live in the package rather than only in `tools/` so an installed copy can
check and export a model without the source tree. `tools/check_model.py` and
`tools/export_schema.py` are thin wrappers over these, so `make model` and
`make export` run exactly what an installed user runs.

Standard library only, like the rest of the package: everything the window's
status line shows is available without a display.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from importlib import metadata

from .check import Checker
from .codes import definition
from .diagnostics import Severity, render
from .export import ExportError, export_schema
from .export import dumps as dump_export
from .persistence import DocumentError, dumps, load
from .stdlib import standard_library

MARKERS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INCOMPLETE: "incomplete",
    Severity.INFO: "note",
}

LEVELS = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "unfinished": Severity.INCOMPLETE,
    "everything": Severity.INFO,
}


def version() -> str:
    try:
        return metadata.version("designer-model")
    except metadata.PackageNotFoundError:  # run from a source checkout
        return "source"


def names_for(model, library) -> dict:
    """Every name a finding might mention, authored or built in."""
    known = {item.uuid: item.name for item in model.index().values()}
    known.update({library.by_name(n).uuid: n for n in library.names})
    return known


def describe(finding, known) -> str:
    code = definition(finding.code)
    return render(code.template, finding.args, known)


def _load(path: pathlib.Path):
    try:
        return load(path), None
    except (OSError, DocumentError, ValueError) as error:
        return None, f"{path}: {error}"


# --- designer-check --------------------------------------------------------------


def check_main(argv: list[str] | None = None) -> int:
    """Load a model, verify it survives a round trip, run the model check, and
    report. Exits non-zero on an error or a failed round trip, so it can gate
    a build."""
    parser = argparse.ArgumentParser(prog="designer-check", description="Check a Designer model file.")
    parser.add_argument("model", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--level",
        choices=list(LEVELS),
        default="warning",
        help=(
            "how much to report; warnings and above by default, because a model "
            "under construction is full of unfinished items and unreferenced types"
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="same as --level warning (kept for habit)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version()}")
    arguments = parser.parse_args(argv)

    document, problem = _load(arguments.model)
    if document is None:
        print(problem, file=sys.stderr)
        return 2

    library = standard_library()
    report = Checker(document, library).run()
    known = names_for(document, library)

    # a document that does not survive a round trip has a persistence bug, and
    # every finding below would be about the wrong model
    round_trip = dumps(document) == arguments.model.read_text()

    if arguments.json:
        blockers = {d.code for d in report.export_blockers}
        print(
            json.dumps(
                {
                    "file": str(arguments.model),
                    "round_trip": round_trip,
                    "counts": {str(k): v for k, v in report.counts().items()},
                    "findings": [
                        {
                            "code": f.code,
                            "severity": str(definition(f.code).severity),
                            "subject": str(f.subject),
                            "message": describe(f, known),
                            "blocks_export": f.code in blockers,
                        }
                        for f in report.findings
                    ],
                },
                indent=2,
            )
        )
        return 1 if report.errors else 0

    kinds = {item.uuid: type(item).__name__ for item in document.index().values()}
    print(f"{arguments.model}")
    print(
        f"  {len(document.contexts)} contexts, {len(document.types)} types, "
        f"{len(document.properties)} properties, {len(document.entities)} entities, "
        f"{len(document.schemas)} schemas, {len(document.validators)} validators"
    )
    print(f"  round trip: {'unchanged' if round_trip else 'DIFFERS'}")
    print(f"  standard library: {len(library)} built-ins, version {library.version}")
    print()

    order = [Severity.ERROR, Severity.WARNING, Severity.INCOMPLETE, Severity.INFO]
    ceiling = order.index(LEVELS[arguments.level])
    shown = 0
    for finding in report.findings:
        severity = definition(finding.code).severity
        if order.index(severity) > ceiling:
            continue
        shown += 1
        owner = kinds.get(finding.subject.item_uuid, "?")
        where = str(finding.subject).split(":", 1)[1] if ":" in str(finding.subject) else ""
        inside = where.partition(".")[2]
        location = f"{owner}" + (f".{inside}" if inside else "")
        print(f"  {MARKERS[severity]:11} {finding.code:8} {location}")
        print(f"                       {describe(finding, known)}")

    counts = report.counts()
    summary = ", ".join(f"{n} {k}" for k, n in counts.items() if n) or "nothing to report"
    print(f"\n  {summary}")
    hidden = len(report.findings) - shown
    if hidden:
        print(f"  {hidden} not shown at --level {arguments.level}")
    if report.export_blockers:
        print(f"  {len(report.export_blockers)} of these would block an export")

    return 1 if report.errors or not round_trip else 0


# --- designer-export --------------------------------------------------------------


def export_main(argv: list[str] | None = None) -> int:
    """Export one Schema (spec §9.6) to standard output or a file. Exits
    non-zero and lists the findings when something the Schema reaches blocks
    the export."""
    parser = argparse.ArgumentParser(prog="designer-export", description="Export one Schema of a Designer model file.")
    parser.add_argument("model", type=pathlib.Path)
    parser.add_argument("schema", help="the Schema's name")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="write here instead of standard output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version()}")
    arguments = parser.parse_args(argv)

    document, problem = _load(arguments.model)
    if document is None:
        print(problem, file=sys.stderr)
        return 2

    schemas = [s for s in document.schemas if s.name == arguments.schema]
    if len(schemas) != 1:
        found = "no" if not schemas else f"{len(schemas)}"
        known = ", ".join(sorted(s.name for s in document.schemas)) or "none"
        print(f"{arguments.model}: {found} Schema named {arguments.schema!r}; there are: {known}", file=sys.stderr)
        return 2

    library = standard_library()
    try:
        exported = export_schema(document, schemas[0].uuid, library)
    except ExportError as error:
        print(f"{arguments.model}: {error}", file=sys.stderr)
        known = names_for(document, library)
        for finding in error.blockers:
            print(f"  {finding.code:8} {describe(finding, known)}", file=sys.stderr)
        return 1

    text = dump_export(exported)
    if arguments.output is None:
        sys.stdout.write(text)
    else:
        arguments.output.write_text(text)
    return 0
