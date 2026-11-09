"""What differs between PostgreSQL, MariaDB and SQLite.

Each dialect answers the same questions: how a name and a string are quoted,
what a base type is stored as, and how each function of the rule language is
written — or that it cannot be, with the reason. Where SQL would mean
something different from the rule, the answer is `Untranslatable`, never an
approximation that passes a different set of values. Appendix *ddl* §4 lists
every mapping.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


class Untranslatable(Exception):
    """A rule this dialect cannot enforce as written. The message says why."""


# Every character str.strip() removes: those for which str.isspace() is true
# (Unicode 15, Python 3.12). Written out, not computed, so the output does not
# change with the Python that runs it.
WHITESPACE_CODES = (
    0x9, 0xA, 0xB, 0xC, 0xD, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680, 0x2000, 0x2001,
    0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200A, 0x2028, 0x2029, 0x202F,
    0x205F, 0x3000,
)


@dataclass(frozen=True)
class Column:
    """What a translation needs to know about a column."""

    name: str
    base: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    keyed: int = 0
    """In a primary key, a foreign key or an index: how many columns of text
    with no length the widest such key holds, this one included. 0 if none."""


class Dialect:
    name = ""
    title = ""
    max_identifier = 63
    true, false = "TRUE", "FALSE"

    # --- names and literals -------------------------------------------------

    def ident(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def string(self, text: str) -> str:
        if "\x00" in text:
            raise Untranslatable("a string holding a NUL character cannot be written in SQL")
        return "'" + text.replace("'", "''") + "'"

    def constraint_name(self, *parts: str) -> str:
        """A name within the dialect's limit: shortened with a hash of the
        whole, so two long names cannot collide when cut."""
        name = "_".join(p for p in parts if p)
        if len(name.encode()) <= self.max_identifier:
            return name
        digest = hashlib.sha1(name.encode()).hexdigest()[:8]  # noqa: S324 - a name, not security
        keep = self.max_identifier - len(digest) - 1
        while len(name[:keep].encode()) > keep:
            keep -= 1
        return f"{name[:keep]}_{digest}"

    # --- types --------------------------------------------------------------

    def column_type(self, column: Column) -> tuple[str, list[str], list[str]]:
        """The type, any checks the type needs to mean the same as the base
        type, and notes for the reader about what the storage does not keep."""
        raise NotImplementedError

    def default(self, tagged: dict[str, object]) -> str:
        ((base, value),) = tagged.items()
        if base == "boolean":
            return self.true if value else self.false
        if base in ("integer", "real", "decimal"):
            return str(value)
        return self.string(str(value))

    # --- the functions of the rule language ---------------------------------

    def length(self, x: str) -> str:
        return f"char_length({x})"

    def lower(self, x: str) -> str:
        return f"lower({x})"

    def upper(self, x: str) -> str:
        return f"upper({x})"

    def strip(self, x: str) -> str:
        raise NotImplementedError

    def concat(self, a: str, b: str) -> str:
        return f"({a} || {b})"

    def starts_with(self, x: str, p: str) -> str:
        raise NotImplementedError

    def ends_with(self, x: str, p: str) -> str:
        raise NotImplementedError

    def contains(self, x: str, p: str) -> str:
        raise NotImplementedError

    def full_match(self, x: str, pattern: str) -> str:
        raise NotImplementedError

    def is_finite(self, x: str) -> str:
        raise NotImplementedError

    def multiple_of(self, a: str, b: str, bases: tuple[str, str]) -> str:
        return f"mod({a}, {b}) = 0"

    def divide(self, a: str, b: str) -> str:
        return f"({a} / {b})"

    def boolean(self, x: str) -> str:
        """A boolean column used as a condition on its own."""
        return x


class PostgreSQL(Dialect):
    name = "postgresql"
    title = "PostgreSQL"
    max_identifier = 63

    def column_type(self, column: Column) -> tuple[str, list[str], list[str]]:
        base = column.base
        if base == "string":
            return (f"varchar({column.length})" if column.length else "text"), [], []
        if base == "integer":
            return "bigint", [], []
        if base == "real":
            return "double precision", [], []
        if base == "boolean":
            return "boolean", [], []
        if base == "date":
            return "date", [], []
        if base == "time":
            return "time", [], ["a time's UTC offset, if written, is not kept: PostgreSQL time has none"]
        if base == "datetime":
            return "timestamptz", [], []
        if base == "decimal":
            p, s = column.precision, column.scale
            notes = []
            if s is not None:
                notes.append(f"a value with more than {s} decimals is rounded to {s}, not refused")
            if p is not None and s is not None:
                return f"numeric({p}, {s})", [], notes
            if s is not None:
                # numeric(p, s) needs a precision; scale() keeps "no limit" on it
                return f"numeric(1000, {s})", [], notes
            if p is not None:
                # numeric(p) would mean numeric(p, 0) and drop the decimals
                return "numeric", [], [f"at most {p} digits is not enforced: numeric(p) would drop the decimals"]
            return "numeric", [], []
        raise Untranslatable(f"no PostgreSQL type for base type {base!r}")

    ICU = '"und-x-icu"'
    """Full Unicode case mapping, as Python's: upper('ß') is 'SS'. The default
    collation keeps 'ß', so the rule would pass a value it refuses."""

    def lower(self, x: str) -> str:
        return f"lower({x} COLLATE {self.ICU})"

    def upper(self, x: str) -> str:
        return f"upper({x} COLLATE {self.ICU})"

    def strip(self, x: str) -> str:
        chars = "".join(f"\\{c:04x}" if c < 0x10000 else f"\\+{c:06x}" for c in WHITESPACE_CODES)
        return f"btrim({x}, U&'{chars}')"

    def starts_with(self, x: str, p: str) -> str:
        return f"starts_with({x}, {p})"

    def ends_with(self, x: str, p: str) -> str:
        return f"(right({x}, char_length({p})) = {p})"

    def contains(self, x: str, p: str) -> str:
        return f"(strpos({x}, {p}) > 0)"

    def full_match(self, x: str, pattern: str) -> str:
        # an ARE's $ matches only at the very end, as Python's fullmatch does
        return f"({x} ~ {self.string('^(?:' + pattern + ')$')})"

    def is_finite(self, x: str) -> str:
        return f"({x} NOT IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8))"


class MariaDB(Dialect):
    name = "mariadb"
    title = "MariaDB"
    max_identifier = 64
    KEY_LENGTH = 768
    """The longest VARCHAR an InnoDB index can hold in utf8mb4 (3072 bytes)."""

    def ident(self, name: str) -> str:
        return "`" + name.replace("`", "``") + "`"

    def string(self, text: str) -> str:
        if "\x00" in text:
            raise Untranslatable("a string holding a NUL character cannot be written in SQL")
        # backslash is an escape character in MariaDB strings
        return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"

    def column_type(self, column: Column) -> tuple[str, list[str], list[str]]:
        base = column.base
        if base == "string":
            if column.length:
                return f"VARCHAR({column.length})", [], []
            if column.keyed:
                # the key's 3072 bytes are shared by its unbounded text columns
                length = self.KEY_LENGTH // column.keyed
                return (
                    f"VARCHAR({length})",
                    [],
                    [f"at most {length} characters: MariaDB cannot index text of any length"],
                )
            return "TEXT", [], []
        if base == "integer":
            return "BIGINT", [], []
        if base == "real":
            return "DOUBLE", [], []
        if base == "boolean":
            return "BOOLEAN", [], []
        if base == "date":
            return "DATE", [], []
        if base == "time":
            return "TIME(6)", [], ["a time's UTC offset, if written, is not kept: MariaDB TIME has none"]
        if base == "datetime":
            return "DATETIME(6)", [], ["MariaDB keeps no time zone: store datetimes in UTC"]
        if base == "decimal":
            p, s = column.precision, column.scale
            notes = []
            if s is not None:
                notes.append(f"a value with more than {s} decimals is rounded to {s}, not refused")
            if p is not None and s is not None:
                return f"DECIMAL({p}, {s})", [], notes
            if s is not None:
                return f"DECIMAL(65, {min(s, 30)})", [], notes
            if p is not None:
                notes.append(f"stored as DECIMAL({p}, 0) would drop the decimals, so it is DECIMAL(65, 30)")
            else:
                notes.append("MariaDB has no unbounded DECIMAL: at most 35 digits before and 30 after the point")
            return "DECIMAL(65, 30)", [], notes
        raise Untranslatable(f"no MariaDB type for base type {base!r}")

    def length(self, x: str) -> str:
        return f"CHAR_LENGTH({x})"

    def lower(self, x: str) -> str:
        raise Untranslatable("MariaDB's LOWER() maps one character to one, as Python's does not")

    def upper(self, x: str) -> str:
        raise Untranslatable("MariaDB's UPPER() leaves 'ß' as it is, where Python's gives 'SS'")

    def strip(self, x: str) -> str:
        chars = "".join(f"\\x{{{c:x}}}" for c in WHITESPACE_CODES)
        return f"REGEXP_REPLACE({x}, {self.string(f'^[{chars}]+|[{chars}]+$')}, '')"

    def concat(self, a: str, b: str) -> str:
        return f"CONCAT({a}, {b})"

    def starts_with(self, x: str, p: str) -> str:
        return f"(LEFT({x}, CHAR_LENGTH({p})) = {p})"

    def ends_with(self, x: str, p: str) -> str:
        return f"(RIGHT({x}, CHAR_LENGTH({p})) = {p})"

    def contains(self, x: str, p: str) -> str:
        return f"(LOCATE({p}, {x}) > 0)"

    def full_match(self, x: str, pattern: str) -> str:
        # PCRE's $ also matches before a final newline; \z is the true end
        return f"({x} REGEXP {self.string('^(?:' + pattern + ')' + chr(92) + 'z')})"

    def is_finite(self, x: str) -> str:
        # a DOUBLE cannot hold NaN or an infinity at all
        return self.true

    def multiple_of(self, a: str, b: str, bases: tuple[str, str]) -> str:
        # ABS: MOD(-2.5, 0.5) is a DECIMAL -0.0, which MariaDB does not take
        # to equal 0
        return f"ABS(MOD({a}, {b})) = 0"


class SQLite(Dialect):
    name = "sqlite"
    title = "SQLite"
    max_identifier = 1000
    true, false = "1", "0"

    def column_type(self, column: Column) -> tuple[str, list[str], list[str]]:
        x = self.ident(column.name)
        base = column.base
        if base == "string":
            return "TEXT", [], []
        if base == "integer":
            return "INTEGER", [], []
        if base == "real":
            return "REAL", [], []
        if base == "boolean":
            return "INTEGER", [f"{x} IN (0, 1)"], []
        if base in ("date", "time", "datetime"):
            return "TEXT", [], [f"SQLite has no {base} type: stored as ISO 8601 text, not checked"]
        if base == "decimal":
            return (
                "NUMERIC",
                [],
                ["SQLite has no exact decimal: beyond 15 significant digits it is binary floating point"],
            )
        raise Untranslatable(f"no SQLite type for base type {base!r}")

    def length(self, x: str) -> str:
        return f"length({x})"

    def lower(self, x: str) -> str:
        raise Untranslatable("SQLite's lower() changes only ASCII letters")

    def upper(self, x: str) -> str:
        raise Untranslatable("SQLite's upper() changes only ASCII letters")

    def strip(self, x: str) -> str:
        return f"trim({x}, char({', '.join(str(c) for c in WHITESPACE_CODES)}))"

    def starts_with(self, x: str, p: str) -> str:
        return f"(substr({x}, 1, length({p})) = {p})"

    def ends_with(self, x: str, p: str) -> str:
        return f"(length({p}) = 0 OR substr({x}, -length({p})) = {p})"

    def contains(self, x: str, p: str) -> str:
        return f"(instr({x}, {p}) > 0)"

    def full_match(self, x: str, pattern: str) -> str:
        raise Untranslatable("SQLite has no regular expressions unless an extension is loaded")

    def divide(self, a: str, b: str) -> str:
        # a decimal column holds 3 as the integer 3, and 3 / 2 would be 1
        return f"(CAST({a} AS REAL) / {b})"

    def is_finite(self, x: str) -> str:
        # SQLite stores NaN as NULL; 9e999 reads as infinity
        return f"(abs({x}) < 9e999)"

    def multiple_of(self, a: str, b: str, bases: tuple[str, str]) -> str:
        if any(base != "integer" for base in bases):
            raise Untranslatable("SQLite's % works on integers only")
        return f"({a} % {b}) = 0"


DIALECTS: dict[str, type[Dialect]] = {"postgresql": PostgreSQL, "mariadb": MariaDB, "sqlite": SQLite}
ALIASES = {"postgres": "postgresql", "pg": "postgresql"}


def dialect(name: str) -> Dialect:
    key = ALIASES.get(name.lower(), name.lower())
    if key not in DIALECTS:
        raise ValueError(f"unknown dialect {name!r}: choose {', '.join(DIALECTS)}")
    return DIALECTS[key]()
