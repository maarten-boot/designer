# Conversation — 9 November 2026

`HISTORY.md` keeps every prompt verbatim; this log keeps what was done about
them, one day per file.

## Turns 193–194: "pushed and tagged", "status?"

- Verified: `main` = `origin/main` at `acd2c1e`; releases v0.4.0–v0.6.0 on
  GitHub; the stray `v0.7.0` tag gone locally and remotely.
- New global working rules noticed: planning files (this folder), WCAG
  contrast. Measured the app's colours on white: five text colours failed AA
  (`#aaaaaa` 2.3, `#999999` 2.9, `#888888` and `#8a8a6a` 3.5, `#777777` 4.48).
- Proposed: (a) planning files, (b) fix contrast and add presets.

## Turn 195: no branch; fix contrast; review Go and a database

The user: planning files stay on the current branch (their own project); fix
the contrast; review the impact of A) Go and B) a database.

Input review: "store our schema in a database" can mean the model catalogue
in a database, or the exported schema created as DDL. The review covers both
and asks which was meant.

Done:

- `designer_app/palette.py` (tkinter-free): every colour as intent, resolved
  to a minimum WCAG ratio; presets AA/AAA/Max plus custom 4.5–21; font cues
  and inverted selections where colour runs out.
- `designer_app/theme.py`: applies a palette to ttk styles, the option
  database, existing classic widgets and Treeview tags, live.
- Settings `contrast` (hand-editable), View ▸ Contrast (presets, Custom
  ratio…), Preferences field. Every hard-coded colour removed from the widget
  modules, with a test that keeps it that way.
- Checked on Tk 8.6.17 by pixel sampling: a selected row is drawn in the
  selection's colours, not its tag's.
- Screenshots at AA and Max under Xvfb looked right.
- `xvfb-run -a make check` green: 1208 tests (was 1154).
- Spec §13.12 added; §13.11, §14.3, §15, README, HANDOVER and RELEASE-NOTES
  (Unreleased) updated.
- `docs/planning/`: Plan.md, Spec.md (CON-1…8, REV-1/2), Tests.md (traced),
  Review-Go-and-Database.md, this log.

Suggested next: a crosscheck of Spec.md, Plan.md and the code before the next
release.

## Turn 196: commit; Go and B1 skipped; frozen build and B2 wanted

Committed the contrast work and planning files. Go and the model-in-a-database
option are dropped. A frozen build is wanted. B2 is to be a separate app
converting the export to PostgreSQL, SQLite and MariaDB; a design was proposed.

## Turn 197: frozen build first; Linux, Windows and macOS via GitHub Actions

- `tools/freeze.py` (PyInstaller; `make freeze`) builds this platform's app
  into `dist-frozen/`, runs its self-test and packages it. Its environment is
  kept in `~/.cache/designer-release/freeze-pyX.Y`; temporary build folders
  are removed afterwards.
- `designer_app/frozen.py` is the frozen entry point: `--bench-worker`,
  `--self-test MODEL REPORT`, or the app. `bench.worker_command()` starts the
  frozen executable as the worker when `sys.frozen` is set.
- The first local build failed its self-test: the library's data files were
  not bundled (`--collect-data` needs the package installed; switched to
  `--add-data`). That is what the self-test is for.
- Folder builds rather than one-file builds, because a one-file build unpacks
  itself at each start and the bench's worker must start within 2 s.
- `.github/workflows/frozen.yml` at the repository root: a matrix build on
  ubuntu-22.04, windows-latest and macos-latest, with a tag/version check;
  on a tag, the archives are attached to the release or to a new draft.
- 1215 tests are green. Spec §14.5, README, HANDOVER, RELEASE-NOTES and the
  planning files are updated.

## Turn 198: commit

Committed the frozen build (`5f2fcb2`).

## Turn 199: "i pushed it" — designer-ddl

- No frozen-build run in Actions yet; the user can start it by hand.
- Built `packages/designer-ddl`: `dialects.py` (PostgreSQL, MariaDB, SQLite),
  `translate.py` (the rule language to SQL, untranslatable by default),
  `generate.py` (tables, keys, indexes, checks, comments, report), `cli.py`
  (`designer-ddl`). Standard library only; reads the export, not the model.
- Verified against real databases in podman (postgres:16 already on the
  machine; mariadb:11.4 pulled): all nine example files apply; probe rows are
  accepted and refused as the rules say.
- `tools/ddl_conformance.py` compares each translated rule with the evaluator
  on sample values. Its first run found four wrong translations, all fixed:
  `strip` missing non-ASCII whitespace; PostgreSQL `upper('ß')` (now ICU);
  SQLite integer division of decimals; MariaDB's decimal `-0.0 <> 0`. It also
  showed MariaDB's UPPER is simple case mapping (now untranslatable).
- MariaDB needed `utf8mb4_nopad_bin` (case and trailing spaces), and the key
  length shared between unbounded text columns (3072-byte key limit).
- `make release` failed on this machine: Debian's python3-tqdm leaves an
  empty `build/` in dist-packages, which looks like the `build` module.
  `release.py` now checks for `build.__main__`.
- `.github/workflows/ddl.yml`: PostgreSQL and MariaDB service containers, the
  examples applied and the conformance run.
- 1260 tests green; `make release` verified with three packages. Appendix
  `docs/designer-ddl.md`; spec §9.6, §14.1, §15; README, HANDOVER,
  RELEASE-NOTES and the planning files updated.

## Turn 200

> yes commit it

Committed designer-ddl (turn 199) on main.
