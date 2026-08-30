"""Check a model file from the command line.

    python3 tools/check_model.py examples/sales.json

Loads the document, verifies it survives a save/load round trip unchanged, runs
the model check, and reports what it finds. Exits non-zero on an error, so it
can gate a build.

This exists because `designer-model` has no interface and no dependencies:
everything the window shows in its status line is available without a display,
which is the point of keeping the domain and the interface apart.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/designer-model/src")
)

from designer_model import Checker, DocumentError, dumps, load
from designer_model.codes import definition
from designer_model.diagnostics import Severity, render
from designer_model.stdlib import standard_library

MARKERS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INCOMPLETE: "incomplete",
    Severity.INFO: "note",
}


def names_for(model, library) -> dict:
    """Every name a finding might mention, authored or built in."""
    known = {item.uuid: item.name for item in model.index().values()}
    known.update({library.by_name(n).uuid: n for n in library.names})
    return known


def describe(finding, known) -> str:
    code = definition(finding.code)
    return render(code.template, finding.args, known)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a Designer model file.")
    parser.add_argument("model", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--level",
        choices=["error", "warning", "unfinished", "everything"],
        default="warning",
        help=(
            "how much to report; warnings and above by default, because a model "
            "under construction is full of unfinished items and unreferenced types"
        ),
    )
    parser.add_argument(
        "--quiet", action="store_true", help="same as --level warning (kept for habit)"
    )
    arguments = parser.parse_args(argv)

    try:
        document = load(arguments.model)
    except (OSError, DocumentError) as error:
        print(f"{arguments.model}: {error}", file=sys.stderr)
        return 2

    library = standard_library()
    report = Checker(document, library).run()
    known = names_for(document, library)

    # a document that does not survive a round trip has a persistence bug, and
    # every finding below would be about the wrong model
    round_trip = dumps(document) == arguments.model.read_text()

    if arguments.json:
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
                            "blocks_export": f.code
                            in {d.code for d in report.export_blockers},
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
    ceiling = order.index(
        {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "unfinished": Severity.INCOMPLETE,
            "everything": Severity.INFO,
        }[arguments.level]
    )
    shown = 0
    for finding in report.findings:
        severity = definition(finding.code).severity
        if order.index(severity) > ceiling:
            continue
        shown += 1
        owner = kinds.get(finding.subject.item_uuid, "?")
        where = (
            str(finding.subject).split(":", 1)[1] if ":" in str(finding.subject) else ""
        )
        inside = where.partition(".")[2]
        location = f"{owner}" + (f".{inside}" if inside else "")
        print(f"  {MARKERS[severity]:11} {finding.code:8} {location}")
        print(f"                       {describe(finding, known)}")

    counts = report.counts()
    summary = (
        ", ".join(f"{n} {k}" for k, n in counts.items() if n) or "nothing to report"
    )
    print(f"\n  {summary}")
    hidden = len(report.findings) - shown
    if hidden:
        print(f"  {hidden} not shown at --level {arguments.level}")
    if report.export_blockers:
        print(f"  {len(report.export_blockers)} of these would block an export")

    return 1 if report.errors or not round_trip else 0


if __name__ == "__main__":
    raise SystemExit(main())
