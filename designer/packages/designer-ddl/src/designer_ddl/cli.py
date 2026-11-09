"""The command, installed as `designer-ddl`.

    designer-ddl EXPORT.json --dialect postgresql|mariadb|sqlite [-o schema.sql] [--strict]

Writes the SQL to standard output or `-o`. The report goes to standard error:
which rules could not be written as CHECK constraints and why, and what the
storage does not keep. `--strict` exits 1 when any rule could not be.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .dialects import ALIASES, DIALECTS, dialect
from .generate import generate, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="designer-ddl", description="SQL table definitions from a Designer schema export."
    )
    parser.add_argument("export", type=pathlib.Path, help="a file written by designer-export")
    parser.add_argument("--dialect", "-d", required=True, help=f"{', '.join(DIALECTS)} (or {', '.join(ALIASES)})")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="write here instead of standard output")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any rule is not enforced by the SQL")
    parser.add_argument("--quiet", "-q", action="store_true", help="no report on standard error")
    parser.add_argument("--version", action="version", version=f"designer-ddl {version()}")
    arguments = parser.parse_args(argv)

    try:
        chosen = dialect(arguments.dialect)
    except ValueError as error:
        parser.error(str(error))
    try:
        document = json.loads(arguments.export.read_text(encoding="utf-8"))
        sql, report = generate(document, chosen)
    except (OSError, ValueError) as error:  # ExportFileError is a ValueError, as is bad JSON
        print(f"designer-ddl: {arguments.export}: {error}", file=sys.stderr)
        return 2

    if arguments.output:
        arguments.output.write_text(sql, encoding="utf-8")
    else:
        sys.stdout.write(sql)
    if not arguments.quiet:
        for line in report.lines():
            print(line, file=sys.stderr)
    return 1 if arguments.strict and report.untranslated else 0


if __name__ == "__main__":
    raise SystemExit(main())
