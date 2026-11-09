"""designer-ddl: the export file to SQL, in three dialects (appendix ddl)."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3

import pytest

from designer_ddl import ExportFileError, Untranslatable, dialect, generate
from designer_ddl.cli import main
from designer_ddl.dialects import WHITESPACE_CODES, Column, MariaDB, PostgreSQL, SQLite
from designer_ddl.translate import translate

ROOT = pathlib.Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
EXPORTS = ["sales_schema", "support_schema", "sales_interfaces"]
DIALECTS = ["postgresql", "mariadb", "sqlite"]


def export(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.export.json").read_text())


def sql_for(rule: str, d, base: str = "string") -> str:
    return translate(rule, d, {"value": Column("value", base)}, value="value")


# --- the acceptance tests: the examples, byte for byte --------------------------


@pytest.mark.parametrize("name", EXPORTS)
@pytest.mark.parametrize("which", DIALECTS)
def test_each_example_gives_its_committed_sql(name, which) -> None:
    sql, _ = generate(export(name), dialect(which))
    assert sql == (EXAMPLES / f"{name}.{which}.sql").read_text()


@pytest.mark.parametrize("name", EXPORTS)
def test_the_sqlite_sql_runs_and_its_constraints_hold(name) -> None:
    db = sqlite3.connect(":memory:")
    db.executescript((EXAMPLES / f"{name}.sqlite.sql").read_text())
    assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {t["name"] for t in export(name)["tables"]}


def test_sqlite_refuses_what_the_rules_refuse() -> None:
    db = sqlite3.connect(":memory:")
    db.executescript((EXAMPLES / "sales_schema.sqlite.sql").read_text())
    customer = "INSERT INTO Customer VALUES ('2026-01-01T00:00:00Z', ?, ?, 'NL')"
    db.execute(customer, ("c1", "Ada"))
    for name in ("", " Ada", "Ada\t", "x" * 81):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(customer, ("c2", name))
    db.execute("INSERT INTO \"Order\" VALUES ('2026-01-01T00:00:00Z', 'ORD-1', 'c1', 'NL', 1.5)")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute("INSERT INTO \"Order\" VALUES ('2026-01-01T00:00:00Z', 'ORD-2', 'c1', 'NL', -1)")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        db.execute("INSERT INTO \"Order\" VALUES ('2026-01-01T00:00:00Z', 'ORD-3', 'nobody', 'NL', 1)")


def test_the_conformance_cases_agree_on_sqlite() -> None:
    """tools/ddl_conformance.py, which CI also runs against PostgreSQL and
    MariaDB: every translated rule agrees with the evaluator on every value."""
    spec = importlib.util.spec_from_file_location("ddl_conformance", ROOT / "tools" / "ddl_conformance.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check(SQLite(), module.run_sqlite) == 0


# --- every rule lands somewhere, and the report says where ----------------------


def test_a_rule_sqlite_cannot_check_is_a_comment_and_in_the_report() -> None:
    sql, report = generate(export("sales_schema"), SQLite())
    assert "-- NOT ENFORCED HERE, enforce in the application: is_uuid (from Uuid)" in sql
    assert any("Customer.id: is_uuid" in line and "no regular expressions" in line for line in report.untranslated)
    assert "CHECK" not in "\n".join(line for line in sql.splitlines() if "regex" in line and "CONSTRAINT" in line)


def test_application_rules_are_listed_not_checked() -> None:
    sql, report = generate(export("sales_schema"), PostgreSQL())
    assert "-- Enforced by the application (not deterministic): in_past" in sql
    assert "--   OrderLine: equals: order.ship_to_country == order.customer.country_code" in sql
    assert report.untranslated == []
    assert len(report.application) == 4


def test_the_export_warnings_are_carried() -> None:
    sql, _ = generate(export("sales_schema"), MariaDB())
    assert "--   MOD602 Auditable:" in sql


def test_names_are_quoted_so_reserved_words_work() -> None:
    assert 'CREATE TABLE "Order" (' in generate(export("sales_schema"), PostgreSQL())[0]
    assert "CREATE TABLE `Order` (" in generate(export("sales_schema"), MariaDB())[0]
    assert PostgreSQL().ident('a"b') == '"a""b"'
    assert MariaDB().ident("a`b") == "`a``b`"


def test_mariadb_compares_text_exactly() -> None:
    """Its default collation ignores case, and _bin ignores trailing spaces:
    `value == upper(value)` would pass anything, `value == strip(value)` too."""
    sql, _ = generate(export("sales_schema"), MariaDB())
    assert sql.count("COLLATE=utf8mb4_nopad_bin") == 3


def test_mariadb_shares_the_key_length_between_text_columns() -> None:
    sql, report = generate(export("support_schema"), MariaDB())
    assert "`customer_id` VARCHAR(384) NOT NULL" in sql
    assert any("Ticket.priority: at most 384 characters" in line for line in report.storage)


def test_foreign_keys_come_after_the_tables_except_in_sqlite() -> None:
    pg, _ = generate(export("sales_schema"), PostgreSQL())
    assert pg.index('ALTER TABLE "Order" ADD CONSTRAINT') > pg.index('CREATE TABLE "OrderLine"')
    lite, _ = generate(export("sales_schema"), SQLite())
    assert "ALTER TABLE" not in lite and 'REFERENCES "Customer" ("id") ON DELETE RESTRICT' in lite


def test_the_same_export_gives_the_same_bytes() -> None:
    assert generate(export("sales_schema"), PostgreSQL())[0] == generate(export("sales_schema"), PostgreSQL())[0]


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"format": "something else"},
        {"format": "designer-schema-export", "format_version": 2},
        {"format": "designer-schema-export", "format_version": 1, "source": {"expression_language": "x"}},
    ],
)
def test_only_an_export_file_is_read(document) -> None:
    with pytest.raises(ExportFileError):
        generate(document, PostgreSQL())


# --- the translation --------------------------------------------------------------


def test_chained_comparisons_become_and() -> None:
    assert (
        sql_for("1 <= len(value) <= 3", PostgreSQL()) == '((1 <= char_length("value")) AND (char_length("value") <= 3))'
    )


def test_numbers_keep_their_spelling() -> None:
    assert sql_for("value >= 0.00", PostgreSQL(), "decimal") == '("value" >= 0.00)'


def test_strings_are_escaped_for_each_dialect() -> None:
    assert sql_for('value == "it\'s \\\\"', PostgreSQL()) == "(\"value\" = 'it''s \\')"
    assert sql_for('value == "it\'s \\\\"', MariaDB()) == "(`value` = 'it''s \\\\')"
    with pytest.raises(Untranslatable, match="NUL"):
        sql_for('value == "a\\x00"', PostgreSQL())


def test_a_pattern_is_anchored_to_the_whole_value() -> None:
    assert sql_for('regex_full_match(value, "[A-Z]{2}")', PostgreSQL()) == "(\"value\" ~ '^(?:[A-Z]{2})$')"
    # PCRE's $ also matches before a final newline
    assert sql_for('regex_full_match(value, "[A-Z]{2}")', MariaDB()) == "(`value` REGEXP '^(?:[A-Z]{2})\\\\z')"


def test_strip_removes_what_python_removes() -> None:
    assert {c for c in range(0x110000) if chr(c).isspace()} == set(WHITESPACE_CODES)


def test_case_mapping_is_the_full_unicode_one_or_not_at_all() -> None:
    assert 'COLLATE "und-x-icu"' in sql_for("value == upper(value)", PostgreSQL())
    for d in (MariaDB(), SQLite()):
        with pytest.raises(Untranslatable):
            sql_for("value == upper(value)", d)


@pytest.mark.parametrize(
    ("rule", "base", "why"),
    [
        ("value < current()", "datetime", "reads the clock"),
        ("value % 2 == 1", "integer", "translates only as"),
        ("value / 2 > 1", "integer", "integer / integer"),
        ("round(value) == value", "decimal", "no SQL translation yet"),
        ("value in options", "string", "list of values written out"),
        ("regex_full_match(value, other)", "string", "is not a column"),
        ("len(value)", "string", "not a condition"),
        ("price > 0", "decimal", "is not a column"),
    ],
)
def test_what_does_not_translate_says_why(rule, base, why) -> None:
    with pytest.raises(Untranslatable, match=why):
        sql_for(rule, PostgreSQL(), base)


def test_long_constraint_names_are_cut_without_colliding() -> None:
    d = PostgreSQL()
    a, b = d.constraint_name("x" * 80, "one"), d.constraint_name("x" * 80, "two")
    assert len(a) <= 63 and len(b) <= 63 and a != b


# --- the command --------------------------------------------------------------------


def test_the_command_writes_the_sql_and_reports_on_stderr(tmp_path, capsys) -> None:
    out = tmp_path / "s.sql"
    assert main([str(EXAMPLES / "sales_schema.export.json"), "-d", "sqlite", "-o", str(out)]) == 0
    assert out.read_text() == (EXAMPLES / "sales_schema.sqlite.sql").read_text()
    assert "could not be written as a CHECK constraint" in capsys.readouterr().err


def test_strict_fails_when_a_rule_is_not_enforced(capsys) -> None:
    source = str(EXAMPLES / "sales_schema.export.json")
    assert main([source, "-d", "sqlite", "--strict", "-q"]) == 1
    assert main([source, "-d", "pg", "--strict", "-q"]) == 0
    assert capsys.readouterr().err == ""


def test_a_file_that_is_not_an_export_is_refused_by_name(tmp_path, capsys) -> None:
    wrong = tmp_path / "model.json"
    wrong.write_text((EXAMPLES / "sales.json").read_text())
    assert main([str(wrong), "-d", "sqlite"]) == 2
    assert "not a schema export" in capsys.readouterr().err


def test_an_unknown_dialect_is_refused() -> None:
    with pytest.raises(SystemExit):
        main([str(EXAMPLES / "sales_schema.export.json"), "-d", "oracle"])
