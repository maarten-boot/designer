# Spec — index and traceable items

The specification proper is `docs/designer-spec-v16.md` and its five
appendices; it is not duplicated here. This file gives the requirements that
`Tests.md` traces to a stable ID, starting with the work done since these
planning files were introduced (9 November 2026). Older behaviour is traced by
the test suite itself (1208 tests at the last run) and by `make docs`.

| Area | Where it is specified |
|---|---|
| Model, application, packaging | `docs/designer-spec-v16.md` |
| Operators and functions | `docs/designer-signature-table.md` |
| The 44 built-in validators | `docs/designer-validator-library.md` |
| Diagnostics (96 codes) | `docs/designer-diagnostics.md` |
| Interfaces and pictures | `docs/designer-interfaces.md` |
| The worked example | `docs/designer-example-notes.md` |

## CON — colour and contrast (spec §13.12)

| ID | Requirement |
|---|---|
| CON-1 | The default is black text (`#000000`) on a white background (`#ffffff`), including the theme's own surfaces. |
| CON-2 | Every foreground/background pair the application draws reaches the chosen minimum WCAG 2 contrast ratio; the default minimum is AA, 4.5:1. |
| CON-3 | Presets AA (4.5:1), AAA (7:1) and Max (21:1, pure black and white only), and a custom minimum from 4.5 to 21. Nothing below AA is offered. |
| CON-4 | The level can be raised interactively — View ▸ Contrast (presets and Custom ratio…) and Edit ▸ Preferences… — and applies at once to what is open. |
| CON-5 | The level is stored in the settings file as `contrast`; a hand-edited preset name in any case, a number, or `"N:1"` is understood, and anything else reads as AA, never an error. |
| CON-6 | A colour that already meets the minimum is unchanged; a failing one is darkened (foreground) or lightened (tint) only as far as needed, keeping its hue. |
| CON-7 | Where colour can no longer distinguish a row state or relationship, another cue stands in: italic for a state, bold for a relationship; a selection that cannot be tinted is inverted. |
| CON-8 | No colour literal appears in any application module except `palette.py`, so every colour is covered by CON-2. |

## FRZ — frozen build (spec §14.5)

| ID | Requirement |
|---|---|
| FRZ-1 | Each release carries the application frozen for Linux x86-64, Windows x86-64 and macOS arm64, with Python and tkinter inside; nothing else to install. |
| FRZ-2 | The frozen app opens a window, finds its bundled library (`stdlib.json` and the rest), and runs the test bench, whose worker is the frozen executable itself started with `--bench-worker`. |
| FRZ-3 | A worker starts fast enough for the bench's two-second limit: a folder build, not a one-file build that unpacks at each start. |
| FRZ-4 | Every build is self-tested on its own platform (`--self-test`) before it is packaged; a failing build is not packaged. |
| FRZ-5 | A tag `vX.Y.Z` builds all three in GitHub Actions, refuses a tag that disagrees with the package versions, and attaches the archives to the release, or to a draft. |
| FRZ-6 | Building never writes an environment or build folder into the repository (the NFS-share rule); output goes to `dist-frozen/`, which is ignored by git. |

## DDL — SQL from an export (appendix *ddl*)

| ID | Requirement |
|---|---|
| DDL-1 | A separate command, `designer-ddl`, reads an export file (never the model) and writes SQL for PostgreSQL, MariaDB or SQLite; standard library only; released with the other packages at one version. |
| DDL-2 | Each table: columns with type, NOT NULL and DEFAULT, primary key, indexes, foreign keys with their ON DELETE; names quoted as designed, so reserved words work. |
| DDL-3 | Each rule becomes a named CHECK constraint only when the dialect says exactly what the rule says; otherwise a `NOT ENFORCED HERE` comment with the reason, listed in the report. Never an approximation. |
| DDL-4 | Rules the export gives to the application (across tables, reading the clock) are listed as comments, not checked. |
| DDL-5 | Where storage keeps less than the model (rounding to a scale, no time zone, bounded key text), the column carries a note and the report lists it. |
| DDL-6 | Output is deterministic: the same export gives the same bytes; the examples are committed and compared byte for byte. |
| DDL-7 | Every translated rule agrees with the designer's evaluator on every sample value, in a real PostgreSQL, MariaDB and SQLite. |
| DDL-8 | `--strict` exits 1 when any rule is not enforced; a file that is not an export exits 2 and says so. |

## TREE — the export as a tree of files (appendix *tree*)

| ID | Requirement |
|---|---|
| TREE-1 | `designer-export MODEL SCHEMA --tree DIR` writes the Schema's export as `schema.json`, one `table.json` per table and one file per column; `--tree` and `-o` exclude each other; the export's gate applies. |
| TREE-2 | Each file holds the export's object unchanged, except that lists of tables and columns become `{name, uuid, path}` entries in the export's order; putting the files back gives the export exactly, key order included. |
| TREE-3 | File names are safe on Linux, Windows and macOS: a name Windows reserves, or one equal to a sibling's when case is ignored, is written `<name>~<uuid>`. Paths are relative to the root and use `/`. |
| TREE-4 | The same export gives the same bytes on every system: UTF-8, `\n` line ends, no timestamp; the worked example's tree is committed and compared byte for byte. |
| TREE-5 | A new tree replaces the old one whole (written beside it, swapped in by rename), leaving no stale file; a target that is neither empty nor a tree is refused (exit 2) and left untouched. |

## PIN — what the workflows run (turn 206, `Pinning.md`)

| ID | Requirement |
|---|---|
| PIN-1 | Every `uses:` names a commit hash, with its release in a comment; every container image a digest, with its tag. |
| PIN-2 | Each pinned item is its latest workable release; where it is not the latest, `Pinning.md` says why. |
| PIN-3 | PyInstaller and everything it installs are installed with `--require-hashes` from `tools/freeze-requirements.txt`, in CI and by `make freeze`. |
| PIN-4 | What cannot be pinned by hash (runner images, apt packages, the Python interpreter) is listed with the reason; runners are named by explicit version, never `-latest`. |

## REV — reviews requested (not requirements)

| ID | Subject | Document |
|---|---|---|
| REV-1 | Impact of moving the code base to Go | `Review-Go-and-Database.md` §A |
| REV-2 | Impact of storing the model (or the exported schema) in a database | `Review-Go-and-Database.md` §B |
