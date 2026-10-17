"""Export one Schema of a model file (spec §9.6).

    python3 tools/export_schema.py examples/sales.json sales_schema
    python3 tools/export_schema.py examples/sales.json sales_schema -o sales.export.json

Writes the export to standard output, or to the file `-o` names. Exits non-zero
and lists the findings when something the Schema reaches blocks the export, so
it can gate a build the way `check_model.py` does.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/designer-model/src")
)

from check_model import describe, names_for
from designer_model import DocumentError, load
from designer_model.export import ExportError, dumps, export_schema
from designer_model.stdlib import standard_library


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export one Schema of a Designer model file."
    )
    parser.add_argument("model", type=pathlib.Path)
    parser.add_argument("schema", help="the Schema's name")
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        help="write here instead of standard output",
    )
    arguments = parser.parse_args(argv)

    try:
        document = load(arguments.model)
    except (OSError, DocumentError) as error:
        print(f"{arguments.model}: {error}", file=sys.stderr)
        return 2

    schemas = [s for s in document.schemas if s.name == arguments.schema]
    if len(schemas) != 1:
        found = "no" if not schemas else f"{len(schemas)}"
        known = ", ".join(sorted(s.name for s in document.schemas)) or "none"
        print(
            f"{arguments.model}: {found} Schema named {arguments.schema!r}; there are: {known}",
            file=sys.stderr,
        )
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

    text = dumps(exported)
    if arguments.output is None:
        sys.stdout.write(text)
    else:
        arguments.output.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
