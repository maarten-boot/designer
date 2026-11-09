# Plan

Kept on `main` (the user's decision, turn 195). `HANDOVER.md` holds the
decisions and the hard-won lessons; this file holds what is being done and
what comes next.

## Released

0.6.0 on GitHub (with 0.4.0 and 0.5.0 before it). The mistaken `v0.7.0` tag
has been deleted locally and remotely.

## Done, unreleased

All on `main` and in RELEASE-NOTES.md's Unreleased section.

- **Contrast** (Spec CON-1 to CON-8, spec §13.12). One palette module holds every
  colour to a minimum WCAG ratio, with AA/AAA/Max/custom, View ▸ Contrast,
  Preferences and the settings file. Five text colours that failed AA are fixed.
  The tests are listed in `Tests.md`.
- **Frozen build** (FRZ-1 to FRZ-6, spec §14.5), turn 197.
- **designer-ddl** (DDL-1 to DDL-8, appendix *ddl*), turn 199.
- **Tree export** (TREE-1 to TREE-5, appendix *tree*), turn 203.
- **Pinned workflows** (PIN-1 to PIN-4, `Pinning.md`), turn 206.

## Reviewed and decided (turn 196)

- **Go** (REV-1): not pursued; the user understands the impact.
- **Model catalogue in a database** (REV-2, B1): not pursued.
- **Frozen build**: done (turn 197); verified on all three platforms by the
  workflow's first run (turn 206). Its actions, images and PyInstaller are now
  pinned by hash (PIN-1 to PIN-4, `Pinning.md`).
- **Schema to DDL** (REV-2, B2): done in turn 199 as `designer-ddl`, all three
  dialects (DDL-1 to DDL-8, appendix *ddl*). Not built yet: migrations,
  triggers, MySQL, a native uuid type (appendix *ddl* §6).

- **Serving the model to programs** (turns 202–203): the readers are
  programs on Linux, Windows and macOS, and a snapshot is enough, so step one
  is a tree of files, done as `designer-export --tree` (TREE-1 to TREE-5,
  appendix *tree*). The aim is application generators, 4GL-like but more
  flexible. A live server (9P or HTTP) is not started; it would serve the same
  tree. Open: whether generators need Types and Validators as files too
  (appendix *tree* §5).

## Open — the user's to decide

1. Context move: refuse it (the spec) or allow it and report (the code)? Spec §10.1.
2. Does an override inherit the slot default it does not replace? Spec §8.1.

## Open — known, not started

- The user's own `sales.json`: the `ip4_addr` pattern `[0-9]{1.3)\(.[0-9]{1,3}){3}`
  does not compile (EXP305). The suggested fix is `[0-9]{1,3}(\.[0-9]{1,3}){3}`. It's
  the user's data, so it hasn't been edited.
- An "edge cases" example file.
- The JSON tab and the Validator operand picker (spec §13.6, `[NOT BUILT]`).

## Crosscheck

Done in turn 206 (Spec.md, Plan.md, Tests.md against the code):

- Every one of the 68 tests named in Tests.md exists, and every Spec.md item
  is traced to a test or to "Not automated". FRZ-6 was untraced; it now has a
  test.
- Spot checks of the requirements against the code: CON-2/CON-3 (each level's
  smallest pair: AA 4.52, AAA 7.01, Max 21, custom 5.5 gives 5.52), CON-5,
  CON-8, DDL-2 (ON DELETE written), FRZ-6. One mismatch: CON-5 promises `"N:1"`
  is understood, but `"5.5 : 1"` with spaces read as AA. Fixed, with a test.
- This file's "Done, unreleased" listed only the contrast work; brought up to
  date.
- The documents that named PostgreSQL 16 and MariaDB 11.4 now name the pinned
  18.6 and 12.3.3.

Next: before the next release.
