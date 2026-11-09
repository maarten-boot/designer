# Designer — appendix: SQL table definitions (`designer-ddl`)

The third package. It reads a Schema's export file (spec §9.6) and writes the
SQL that creates it in PostgreSQL, MariaDB or SQLite. Built in turn 199, from
the review of turn 195 (option B2) and the user's choice in turn 196: a
separate application, not a feature of the editor.

---

## 1. Use

    designer-export model.json sales_schema -o sales_schema.export.json
    designer-ddl sales_schema.export.json --dialect postgresql -o sales_schema.sql

| Option | Meaning |
|---|---|
| `--dialect`, `-d` | `postgresql` (or `postgres`, `pg`), `mariadb`, `sqlite` |
| `-o` | write the SQL here instead of standard output |
| `--strict` | exit 1 if any rule could not be written as a CHECK constraint |
| `--quiet`, `-q` | no report on standard error |

Exit status 2 for a file that cannot be read or is not an export.
`make sql DIALECT=mariadb` runs it on the worked example.

**Standard library only, and no dependency on `designer-model`.** It reads the
export file and nothing else: the export already has every rule resolved,
composites expanded, inherited columns flattened and reference columns named,
which is what the export format was designed for. It is released with the other
two packages, at the same version (spec §14.1).

---

## 2. Every rule ends up in one place

Each rule in the export is one of:

1. **A named CHECK constraint**, when the dialect can say exactly what the rule
   says. Its name is `<table>_<column>_<rule>`, its message a comment above it.
2. **A comment marked `NOT ENFORCED HERE`**, when it cannot, with the reason. It
   is listed in the report too, and `--strict` fails on it. It must be enforced
   by the application.
3. **A comment saying the application enforces it**, when the export already put
   it there: a rule across tables, or one that reads the clock (spec §9.4).

**A translation is exact or it is not made.** A rule is never replaced by SQL
that passes a different set of values. Where a database stores less than the
model says, the column carries a comment and the report a storage note (§4.1).

---

## 3. The output

Deterministic: the same export gives the same bytes, and the tool's version is
not written into it, so a version bump changes nothing. The examples are compared
byte for byte (§5).

- A header naming the Schema, the dialect and the export format, and the
  export's warnings.
- One `CREATE TABLE` per table, in export order: columns with type, `NOT NULL`
  and `DEFAULT`, the primary key, then the checks, column rules first.
  Descriptions become `COMMENT ON` (PostgreSQL), `COMMENT` (MariaDB) or `--`
  comments (SQLite).
- Indexes, then the default order as a comment (SQL has no equivalent).
- Foreign keys after every table exists (`ALTER TABLE … ADD CONSTRAINT`), so
  the order of tables never matters. SQLite cannot add a constraint later, so
  there they are inline, and the file starts with `PRAGMA foreign_keys = ON;`,
  since SQLite checks foreign keys only on connections that ask.
- The cross-table rules, as comments.

**Names are quoted as designed**, never folded: `"Order"` (PostgreSQL, SQLite),
`` `Order` `` (MariaDB). That makes reserved words safe, and means queries must
quote mixed-case names too. A constraint name longer than the dialect allows
(63 bytes in PostgreSQL, 64 in MariaDB) is cut and given a hash of the whole,
so two long names cannot collide.

---

## 4. The mappings

### 4.1 Types

| Base | PostgreSQL | MariaDB | SQLite |
|---|---|---|---|
| `string` | `varchar(n)` with a length, else `text` | `VARCHAR(n)`, else `TEXT`; in a key, `VARCHAR(768 / k)` | `TEXT` |
| `integer` | `bigint` | `BIGINT` | `INTEGER` |
| `real` | `double precision` | `DOUBLE` | `REAL` |
| `decimal` | `numeric(p, s)`; `numeric(1000, s)` with only a scale; `numeric` | `DECIMAL(p, s)`; `DECIMAL(65, s)`; `DECIMAL(65, 30)` | `NUMERIC` |
| `boolean` | `boolean` | `BOOLEAN` | `INTEGER`, checked to be 0 or 1 |
| `date` | `date` | `DATE` | `TEXT` (ISO 8601) |
| `time` | `time` | `TIME(6)` | `TEXT` |
| `datetime` | `timestamptz` | `DATETIME(6)` | `TEXT` |

Storage notes, written beside the column and in the report:

- **A decimal with a scale is rounded to it, not refused.** That is how
  `numeric(p, s)` and `DECIMAL(p, s)` behave, before any CHECK sees the value.
  The model's `max_scale` refuses instead. A precision without a scale is not
  enforced in PostgreSQL, since `numeric(p)` would mean no decimals at all.
- **MariaDB cannot index text of any length**: a key's 3072 bytes are shared by
  its unbounded text columns, 768 characters for one, 384 each for two.
- **MariaDB keeps no time zone**: store datetimes in UTC. A time's offset is
  kept by neither PostgreSQL's `time` nor MariaDB's `TIME`.
- **SQLite has no exact decimal and no date types**; its column types are not
  enforced either.

**MariaDB tables use `utf8mb4_nopad_bin`.** MariaDB's default collation ignores
case, which would make `value == upper(value)` pass anything, and plain
`utf8mb4_bin` ignores trailing spaces, which would make `value == strip(value)`
pass `"abc "`. With this collation text compares exactly, as it does in the
rule.

### 4.2 Operators

`and`, `or`, `not`, the six comparisons, chained comparisons (`1 <= x <= 3`
becomes `1 <= x AND x <= 3`), `in` and `not in` with a written-out list, `+`,
`-`, `*` and `/` on numbers, and `+` on strings as concatenation. Numbers keep
their spelling, so `0.00` stays `0.00`.

- **`/`** is refused for two integers, which the rule language divides exactly
  and SQL truncates. In SQLite it divides as real numbers, because a decimal
  column holds `3` as the integer 3.
- **`%`** translates only as `x % n == 0` or `!= 0`. Python floors a negative
  remainder and SQL truncates it, so only a zero test means the same in both.
  MariaDB's is written `ABS(MOD(x, n)) = 0`: `MOD(-2.5, 0.5)` is a decimal
  `-0.0`, which MariaDB does not take to equal 0. SQLite's `%` works on
  integers only.

### 4.3 Functions

| Function | PostgreSQL | MariaDB | SQLite |
|---|---|---|---|
| `len` | `char_length` | `CHAR_LENGTH` | `length` |
| `lower`, `upper` | `lower(x COLLATE "und-x-icu")` | not translated | not translated |
| `strip` | `btrim(x, U&'…')` | `REGEXP_REPLACE` | `trim(x, char(…))` |
| `starts_with` | `starts_with` | `LEFT … =` | `substr … =` |
| `ends_with` | `right … =` | `RIGHT … =` | `substr(x, -n) =` |
| `contains` | `strpos … > 0` | `LOCATE … > 0` | `instr … > 0` |
| `regex_full_match` | `x ~ '^(?:p)$'` | `x REGEXP '^(?:p)\z'` | not translated |
| `is_finite` | `NOT IN (NaN, ±Infinity)` | always true | `abs(x) < 9e999` |

- **`lower` and `upper` must map cases as Python does**: `upper('ß')` is `'SS'`.
  PostgreSQL's default collation keeps `'ß'`, so the ICU collation is named,
  which needs a PostgreSQL built with ICU (the official images and the major
  distributions' packages are). MariaDB maps one character to one, and SQLite
  only ASCII letters, so neither is translated.
- **`strip` removes exactly what Python's does**: every character for which
  `str.isspace()` is true, Unicode included, listed in
  `designer_ddl/dialects.py` as `WHITESPACE_CODES`. SQL's plain `TRIM` removes
  only spaces.
- **A pattern must match the whole value**, as `fullmatch` does. PCRE's `$` also
  matches before a final newline, so MariaDB's pattern ends in `\z`. Patterns
  are passed through otherwise. The three regex flavours agree on what the
  built-ins use, which §5 checks, but a pattern with Python-only syntax may be
  refused by the database or mean something else there. SQLite has regular
  expressions only with an extension, so they are not translated.
- **Not translated yet**: `abs`, `round`, `min`, `max`, the conversions, the
  durations and `precision`/`scale` (the export turns those two into storage
  anyway). The clock functions are never translated: a check constraint must
  not read the clock.

---

## 5. How it is checked

1. **The examples, byte for byte.** `examples/<schema>.<dialect>.sql` for each of
   the three exports and three dialects, nine files, generated and compared by
   the tests, and reproduced by the installed package in `make release`.
2. **The SQLite files run**, in the test suite: they apply, and refuse rows the
   rules refuse.
3. **Conformance with the evaluator.** `tools/ddl_conformance.py` (`make
   conformance`) takes 48 rules covering every operator and function above,
   with 2 to 41 sample values each, among them `'ß'`, `'İ'`, a no-break space
   and a trailing newline. It stores the values in a table of the dialect's own
   type and collation, asks the database for each rule's verdict, and compares
   it with `designer_model`'s evaluator. A translated rule must agree on every
   value. SQLite runs in the test suite. PostgreSQL and MariaDB run from the
   workflow `.github/workflows/ddl.yml`, against PostgreSQL 16 and MariaDB 11.4,
   which also applies every committed example.

The first run of step 3 found four translations that were wrong, and each is
now a rule above:
- `strip` missed non-ASCII whitespace;
- PostgreSQL's `upper('ß')`;
- SQLite's integer division;
- MariaDB's negative zero.

---

## 6. Not built

- Migrations: changing an existing database when the model changes means
  comparing two exports, and is a project of its own.
- Triggers for `enforcement = database` rules that a CHECK cannot express
  (spec §9.4).
- MySQL. Its CHECK and regex support differ from MariaDB's, so it would be a
  fourth dialect, not an alias.
- A native `uuid` type for PostgreSQL. A string checked by `is_uuid` stays
  `text`, so the check means the same everywhere.
