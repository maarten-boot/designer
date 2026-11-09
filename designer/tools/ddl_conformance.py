"""Do the translated rules say what the rules say? Ask a real database.

    python3 tools/ddl_conformance.py                       SQLite, in-process
    python3 tools/ddl_conformance.py --psql "psql -U postgres"
    python3 tools/ddl_conformance.py --mariadb "mariadb -u root -px test"

For every case — a rule as the export writes it, and sample values — it stores
the values in a one-column table of the type the dialect's DDL would use
(MariaDB's collation included, since that is what decides how text compares),
asks the database for the translated condition on each row, and compares with
the designer's own evaluator. A rule that does not translate for the dialect
is skipped and listed; one that translates must agree on every value. A
client command reads SQL on standard input, so a database in a container
works: `--psql "podman exec -i pg psql -U postgres"`.

The cases cover every function and operator `designer_ddl.translate` writes,
through the built-in validators that use them (appendix *ddl* §5).
"""

from __future__ import annotations

import argparse
import pathlib
import shlex
import sqlite3
import subprocess
import sys
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[1]
for package in ("designer-model", "designer-ddl"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from designer_ddl.dialects import (
    Column,
    Dialect,
    MariaDB,
    PostgreSQL,
    SQLite,
    Untranslatable,
    dialect,
)
from designer_ddl.translate import translate
from designer_model.expressions.evaluate import evaluate_leaf

TEXT = ["", "a", "abc", "ABC", "Abc", " abc", "abc ", "ab\n", "\tab", "a b", "abcd", "é", "É", "ß",
        "ORD-123456", "ORD-12345", "x@y.z", "@y.z", "https://e.org/x", "http:/x", "NL", "nl", "NLD",
        "0c0ffee0-0000-4000-8000-000000000001", "abc ", "a_1", "1a", "it's", "back\\slash",
        "SS", "İ", "i\u0307", "ΑΣ", "ας", "ﬁ", "FI", "ǆ", "Ǆ", "\u3000abc", "\u2028x", "x\x85"]  # fmt: skip
INTEGERS = [-7, -3, -1, 0, 1, 2, 3, 5, 6, 7, 10, 100]
DECIMALS = [Decimal(x) for x in ("-2.5", "-1", "0", "0.5", "1", "2.25", "3", "10.5")]
REALS = [-2.5, -1.0, 0.0, 0.5, 1.0, 3.0, 1e300]
BOOLEANS = [True, False]

CASES: list[tuple[str, str, list]] = [
    # (base, the rule as exported, values)
    ("string", "len(value) <= 3", TEXT),
    ("string", "len(value) >= 2", TEXT),
    ("string", "len(value) == 3", TEXT),
    ("string", "2 <= len(value) <= 3", TEXT),
    ("string", "len(value) > 0", TEXT),
    ("string", "value == strip(value)", TEXT),
    ("string", "(len(value) > 0) and (value == strip(value))", TEXT),
    ("string", "value == lower(value)", TEXT),
    ("string", "value == upper(value)", TEXT),
    ("string", 'starts_with(value, "ab")', TEXT),
    ("string", 'ends_with(value, "bc")', TEXT),
    ("string", 'ends_with(value, "")', TEXT),
    ("string", 'contains(value, "b")', TEXT),
    ("string", 'contains(value, "\'")', TEXT),
    ("string", 'value in ["abc", "ABC", "it\'s"]', TEXT),
    ("string", 'value not in ["abc", "ABC"]', TEXT),
    ("string", 'value == "abc"', TEXT),
    ("string", 'value != "abc"', TEXT),
    ("string", 'value + "x" == "abcx"', TEXT),
    ("string", 'regex_full_match(value, "[A-Z]{2}")', TEXT),
    ("string", 'regex_full_match(value, "ORD-[0-9]{6}")', TEXT),
    ("string", 'regex_full_match(value, "[^@\\\\s]+@[^@\\\\s]+\\\\.[^@\\\\s]+")', TEXT),
    ("string", 'regex_full_match(value, "https?://[^\\\\s]+")', TEXT),
    ("string", 'regex_full_match(value, "[A-Za-z_][A-Za-z0-9_]*")', TEXT),
    (
        "string",
        'regex_full_match(value, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")',
        TEXT,
    ),
    (
        "string",
        '(regex_full_match(value, "ORD-[0-9]{6}")) or (regex_full_match(value, "[A-Z]{2}"))',
        TEXT,
    ),
    ("string", 'not (regex_full_match(value, "[a-z]+"))', TEXT),
    ("integer", "value >= 0", INTEGERS),
    ("integer", "value > 0", INTEGERS),
    ("integer", "value < 0", INTEGERS),
    ("integer", "1 <= value <= 6", INTEGERS),
    ("integer", "value % 3 == 0", INTEGERS),
    ("integer", "value % 3 != 0", INTEGERS),
    ("integer", "value in [1, 2, 3]", INTEGERS),
    ("integer", "value * 2 - 1 > 4", INTEGERS),
    ("integer", "-value > 2", INTEGERS),
    ("decimal", "value >= 0", DECIMALS),
    ("decimal", "value > 0.5", DECIMALS),
    ("decimal", "value <= 2.25", DECIMALS),
    ("decimal", "value % 0.5 == 0", DECIMALS),
    ("decimal", "value / 2 > 1", DECIMALS),
    ("decimal", "value in [0.5, 1, 3]", DECIMALS),
    ("real", "value >= 0", REALS),
    ("real", "value < 1.5", REALS),
    ("real", "is_finite(value)", REALS),
    ("boolean", "value", BOOLEANS),
    ("boolean", "not value", BOOLEANS),
    ("boolean", "value == True", BOOLEANS),
]


def literal(d: Dialect, base: str, value: object) -> str:
    if base == "boolean":
        return d.true if value else d.false
    if base == "string":
        return d.string(str(value))
    if value == float("inf"):
        return "9e999" if isinstance(d, SQLite) else "'Infinity'::float8"
    return repr(value) if isinstance(value, float) else str(value)


def script(d: Dialect, cases: list[tuple[int, str, str, list]]) -> str:
    """One table per case, its values, and a query giving each verdict."""
    lines = []
    for n, base, sql, values in cases:
        kind, _, _ = d.column_type(Column("value", base))
        table = d.ident(f"conformance_{n}")
        tail = (
            " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_nopad_bin"
            if isinstance(d, MariaDB)
            else ""
        )
        lines.append(f"DROP TABLE IF EXISTS {table};")
        lines.append(
            f"CREATE TABLE {table} (i INTEGER PRIMARY KEY, {d.ident('value')} {kind}){tail};"
        )
        for i, v in enumerate(values):
            lines.append(f"INSERT INTO {table} VALUES ({i}, {literal(d, base, v)});")
        verdict = f"CASE WHEN {sql} THEN 1 ELSE 0 END"
        lines.append(f"SELECT {n}, i, {verdict} FROM {table} ORDER BY i;")
        lines.append(f"DROP TABLE {table};")
    return "\n".join(lines) + "\n"


def run_sqlite(sql: str) -> list[tuple[int, int, int]]:
    db = sqlite3.connect(":memory:")
    rows: list[tuple[int, int, int]] = []
    for statement in sql.split(";\n"):
        if statement.strip():
            rows += db.execute(statement).fetchall()
    return rows


def run_client(command: str, sql: str, flags: list[str]) -> list[tuple[int, int, int]]:
    done = subprocess.run(
        [*shlex.split(command), *flags],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"the client failed:\n{done.stderr}")
    rows = []
    for line in done.stdout.splitlines():
        parts = line.replace("|", "\t").split("\t")
        if len(parts) == 3 and all(p.strip().lstrip("-").isdigit() for p in parts):
            rows.append(tuple(int(p) for p in parts))
    return rows  # type: ignore[return-value]


def check(d: Dialect, runner) -> int:
    chosen: list[tuple[int, str, str, list]] = []
    skipped = []
    for n, (base, rule, values) in enumerate(CASES):
        try:
            sql = translate(rule, d, {"value": Column("value", base)}, value="value")
        except Untranslatable as why:
            skipped.append(f"{rule}: {why}")
            continue
        if isinstance(d, SQLite) and base == "real":
            values = [v for v in values if v != 1e300] + [float("inf")]
        chosen.append((n, base, sql, values))
    rows = runner(script(d, chosen))
    got = {(n, i): verdict for n, i, verdict in rows}
    wrong = []
    for n, base, sql, values in chosen:
        rule = CASES[n][1]
        for i, value in enumerate(values):
            expected = evaluate_leaf(rule, value)
            if (n, i) not in got:
                wrong.append(f"{rule} on {value!r}: no answer from the database")
            elif bool(got[n, i]) != expected:
                wrong.append(
                    f"{rule} on {value!r}: rule says {expected}, {d.title} says {bool(got[n, i])}\n    {sql}"
                )
    print(
        f"{d.title}: {len(chosen)} rules on {sum(len(c[3]) for c in chosen)} values, {len(skipped)} skipped"
    )
    for line in skipped:
        print(f"  skipped: {line}")
    for line in wrong:
        print(f"  WRONG: {line}")
    return 1 if wrong else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--psql", help="a psql command reading standard input")
    parser.add_argument(
        "--mariadb",
        help="a mariadb client command reading standard input, with a database chosen",
    )
    arguments = parser.parse_args()
    status = check(dialect("sqlite"), run_sqlite)
    if arguments.psql:
        status |= check(
            PostgreSQL(),
            lambda sql: run_client(
                arguments.psql, sql, ["-At", "-q", "-v", "ON_ERROR_STOP=1"]
            ),
        )
    if arguments.mariadb:
        status |= check(
            MariaDB(), lambda sql: run_client(arguments.mariadb, sql, ["-N", "-B"])
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
