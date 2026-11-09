# Review: moving to Go, and storing the model in a database

Prepared 9 November 2026 (turn 195), against `main` after 0.6.0 plus the
contrast work. This is an impact review only: nothing has been changed.

## The code as it stands

| Part | Python lines | What it is |
|---|---|---|
| `designer-model` core | 6,044 | items, persistence, derivation, the model check (1,019), export (604), pictures (578), diagnostics registry (564), commands/undo, session, bench, CLI |
| `designer-model` expressions | 1,675 | tokenizer, composite parser, type inference (557), signature table, sandbox, evaluator |
| `designer-app` | 7,418 | tkinter UI: `app.py` (1,544), `forms.py` (1,258), `dialogs.py` (896) and others; about half is tkinter-free logic |
| tests | 11,255 | 1,208 tests (pytest), plus golden files in `examples/` |
| data | 40 KB | `stdlib.json` (44 built-ins), `examples.json`, `deprecations.json` |

Three facts shape both questions:

1. **The model package is self-contained.** It uses the standard library only,
   never imports tkinter, and sits behind a small surface: `load`/`dump`/`save`
   in `persistence.py`, `Session`, `check`, `export`, and the CLI. The app
   talks to it only through that surface.
2. **The language-neutral parts are already files.** The JSON model format
   (`schema_version` 1 and 2), the resolved export format (spec §9.6), the 96
   diagnostic codes and the 44 built-ins are all specified and stored as data.
   `examples/*.export.json` are compared byte for byte.
3. **The expression language is Python syntax.** Rules are parsed with
   `ast.parse`, whitelisted by `sandbox.scan`, typed by `infer.py`, and
   evaluated with `eval` with no built-ins. Patterns use Python's `re`. That is
   the deepest tie to Python.

---

## A. Moving to Go

### What carries over unchanged

- **The file formats**: the model JSON, the export JSON and the settings file.
  Existing models open in a Go build if the loader keeps the same rules
  (lowest `schema_version`, one spelling per literal, nullable references).
- **The specification and appendices**: they describe behaviour, not Python.
  `tools/check_docs.py` would need porting or re-pointing (it imports the
  registry and the library).
- **The golden files**: `examples/sales*.json` and the three `*.export.json`
  become the cross-language conformance suite. This is the single most
  valuable asset for a port: a Go build is right when it produces the same
  bytes and the same findings.

### What has to be rewritten, by risk

| Area | Impact | Why |
|---|---|---|
| **Expression language** (1,675 lines) | **High** | Go has no `ast.parse` for Python syntax. It needs a hand-written lexer and parser for the whitelisted subset, with Python's semantics exactly: chained comparisons (`a < b < c`), `in`/`not in` on lists, `%` on negatives (Python floors where Go truncates), and the integer/decimal/real promotion rules of the signature table. In return `eval` goes away, and with it the sandbox's reason to exist. |
| **Regular expressions** | **High**, and it changes behaviour | Go's `regexp` is RE2: no backreferences and no lookaround, and `\d`/`\w` are ASCII-only, where Python's are Unicode. A pattern valid today (`EXP305` passes) could be refused, or match differently. The spec would have to name a dialect, and existing models would need a migration check. In return RE2 runs in linear time: the test bench's subprocess and `bench.TIMEOUT`, which exist only to kill a runaway Python regex, could go. |
| **Decimal arithmetic** | Medium | Python's `decimal` (and the `_Exact` fraction literal) has no Go standard-library twin. `math/big.Rat` keeps the model package dependency-free; `shopspring/decimal` is simpler but is a dependency. Rounding and the canonical literal spellings must match byte for byte. |
| **Pictures** (578 lines) | Medium | Number/date/time formatting and lenient parsing, including the INT202 round trip over `PROBES`. Go's `time` layout model is unlike Python's; this is a careful port, not a translation. |
| **JSON output** | Medium | `encoding/json` sorts map keys and escapes `<`, `>` and `&` by default; Python's `json.dumps` keeps insertion order. Byte-identical export needs ordered structs or a small custom writer, and `SetEscapeHTML(false)`. |
| **Model check, derivation, export, commands, session** | Medium, mostly volume | Straight logic. Dataclasses become structs; the `Item` hierarchy becomes an interface with a type switch. Expect 1.5–2× the line count. |
| **The GUI** (7,418 lines) | **High** | No tkinter in Go. The realistic options are Fyne, Gio, or a local web UI (Wails, or a plain HTTP server with a browser page). Every widget module is rewritten. The tkinter-free logic (`forms.py`, `rows.py`, `selection.py`, `palette.py` and others, about half) ports like the model. The contrast work (§13.12) ports as logic, but how a toolkit exposes tag fonts and selection colours differs. |
| **Tests** (11,255 lines) | High, mostly volume | 1,208 pytest tests become Go table tests. The golden files carry over as they are. The widget tests (`test_widgets.py`, run under Xvfb) depend on the toolkit chosen. |

### What Go would gain

- **One binary per platform.** No Python 3.12+, no venv, no `python3-tk`, no
  `make release` building wheels. This is the strongest argument, and the
  release history (version/tag mismatches, "Text file busy", the release venv)
  was mostly packaging pain.
- **Speed** in the model check on large models. It is not a problem at the
  current size: a full check of the worked example is instant.
- **Linear-time regex** (above), and no `eval`.

### What it would cost

- A rewrite of roughly 15,000 lines of source and 11,000 of tests, with the
  expression semantics and the regex dialect as real behaviour changes rather
  than translation.
- A freeze or a dual-maintenance period: every fix during the port lands twice.
- The lessons in `HANDOVER.md` ("What keeps going wrong") are about this code
  base. Most transfer, but the widget-test ones would have to be relearned for
  a new toolkit.

### Recommendation for A

Don't port the whole thing now. If the driver is **distribution**, try a
cheaper route first: a frozen build (PyInstaller or Nuitka) gives a
single-file app per platform with tkinter included, and costs days, not months.

If Go is wanted anyway, port in this order, so it stays shippable at each step:

1. **`designer-model` and the CLI** (`designer-check`, `designer-export`) to
   Go, held to the golden files and the findings of `examples/sales*.json`.
   Decide the regex dialect first: write it into the spec, and add a check
   that flags existing patterns RE2 refuses.
2. Run both implementations against the same corpus until they agree.
3. Only then the GUI, on the toolkit chosen. The Python app can use the Go
   CLI in the meantime, or keep its own model package.

---

## B. Storing the model in a database

The question can be read two ways, and the costs are very different. Please
confirm which one you meant.

### B1. The model catalogue in a database, instead of a JSON file

Spec §12 already allows for this as `[V2]`: "a SQLAlchemy-backed store for the
catalogue itself, behind the repository interface (`load`, `save`,
`items_in_context`, `references_to`)".

**Where it touches the code**

| Area | Impact | Notes |
|---|---|---|
| `persistence.py` (448 lines) | Medium | A second backend beside JSON: tables per item kind, as in the flat JSON (§12), with UUID keys. Paths, bindings, arguments and indexes become child tables, or JSON columns. Expressions stay text. |
| `Session` (225 lines) | Medium | Open/save become connect/commit. **Autosave and crash recovery** (§12.1) change meaning: a database commit is already durable, so the autosave file may no longer be needed, or it becomes a transaction per command. |
| `commands.py`, undo | Low if whole-model, high if incremental | Today every command edits the in-memory graph, and save writes it whole. Keep that (load all, write all) and only persistence changes. Write per command, and every command needs a database form, and undo must be inverse SQL or an in-memory stack kept in step. |
| `check.py`, `derive.py`, `export.py` | **None**, if the whole model stays in memory | They work on the in-memory graph. Querying the database instead (`items_in_context`, `references_to`) is only worth it for models far larger than now. |
| The app | Low | File ▸ Open/Save become connection choices; Open Recent holds connection strings. Store credentials outside `settings.json`. |
| `schema_version` / `library_version` | Medium | They become schema migrations for the database's own tables. |
| Git workflow | **Lost** | The one-file-per-model JSON "diffs well in git" (§12) — that was the reason for choosing it. A database needs an export to JSON to keep reviewable history. The JSON format should stay as the interchange format either way. |

**What it gains**: several people editing one catalogue at once, but only with
a server database (PostgreSQL), and only with locking or merge rules that do
not exist yet. It also gains queries across many models.
**SQLite** gives neither: it is one file like the JSON, but not diffable.

**Recommendation for B1**: worth it only if multi-user editing is the goal.
If so, keep the in-memory model and whole-model check, add a repository
backend behind `load`/`save` (PostgreSQL via SQLAlchemy, a new dependency for
the model package, or kept in a separate `designer-store` package so the
model stays standard-library only), and keep JSON as the export/backup format.
Settle the concurrency rule (lock per context? last writer wins? merge?)
before writing any code.

### B2. The exported schema created in a database (DDL)

Spec §15 lists this as deferred: "Export: DDL, SQLAlchemy declarative classes,
or Pydantic models, one Schema at a time".

| Area | Impact | Notes |
|---|---|---|
| `export.py` | Low–medium | The resolved export (§9.6) already has everything: tables per concrete entity (flattened, §8), columns with resolved types, constraints, indexes, default order. A DDL writer is a new consumer of that JSON, best as a separate tool, like the YAML decision (turn 138). |
| Types | Medium | Mapping the eight base types and pictures to one SQL dialect (PostgreSQL first): `decimal` precision and scale, `datetime` with time zone, `uuid`. |
| Validators | Medium | Rules marked `enforcement = database` become `CHECK` constraints. Cross-entity rules stay in the application (a decided rule). A clock rule is already refused for the database (`MOD605`). Patterns need the database's regex dialect, which is the same dialect question as A. Triggers stay `[V2]` (§9.4). |
| Migrations | High, if wanted | Creating a schema is easy. Changing an existing database when the model changes means diffing two exports: a separate project. |

**Recommendation for B2**: a good next feature, and cheap compared with B1:
a `designer-ddl` tool that reads `*.export.json` and writes PostgreSQL DDL,
with golden-file tests like the export's. Leave migrations out at first.

---

## Summary

| | Effort | Risk | Main benefit | Recommendation |
|---|---|---|---|---|
| A. Go | Months: about 15k source lines and 11k test lines | High: expression semantics, regex dialect, GUI toolkit | One binary, no Python runtime | Try a frozen Python build first; if Go, port the model and CLI first, against the golden files |
| B1. Model in a DB | Weeks | Medium: concurrency, loss of git diffs | Multi-user editing | Only for multi-user; a separate store package; keep JSON |
| B2. Schema to DDL | Days to a couple of weeks | Low | Real databases from the model | Recommended next; a separate tool reading the export JSON |
