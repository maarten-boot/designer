# Plan

Kept on `main` (the user's decision, turn 195). `HANDOVER.md` holds the
decisions and the hard-won lessons; this file holds what is being done and
what comes next.

## Released

0.6.0 on GitHub (with 0.4.0 and 0.5.0 before it). The mistaken `v0.7.0` tag
has been deleted locally and remotely.

## Done, unreleased

- **Contrast** (Spec CON-1 to CON-8, spec §13.12). One palette module holds every
  colour to a minimum WCAG ratio, with AA/AAA/Max/custom, View ▸ Contrast,
  Preferences and the settings file. Five text colours that failed AA are fixed.
  The tests are listed in `Tests.md`.

## Reviewed and decided (turn 196)

- **Go** (REV-1): not pursued; the user understands the impact.
- **Model catalogue in a database** (REV-2, B1): not pursued.
- **Frozen build**: done (turn 197), Linux verified here; Windows and macOS
  are verified by the workflow's first run (FRZ-1 to FRZ-6).
- **Schema to DDL** (REV-2, B2): wanted as a separate app targeting
  PostgreSQL, SQLite and MariaDB. Design proposed in turn 196. Next, after
  the frozen build (turn 197), starting with PostgreSQL.

## Open — the user's to decide

1. Context move: refuse it (the spec) or allow it and report (the code)? Spec §10.1.
2. Does an override inherit the slot default it does not replace? Spec §8.1.

## Open — known, not started

- The user's own `sales.json`: the `ip4_addr` pattern `[0-9]{1.3)\(.[0-9]{1,3}){3}`
  does not compile (EXP305). The suggested fix is `[0-9]{1,3}(\.[0-9]{1,3}){3}`. It's
  the user's data, so it hasn't been edited.
- An "edge cases" example file.
- The JSON tab and the Validator operand picker (spec §13.6, `[NOT BUILT]`).

## Next crosscheck

After the contrast work: Spec.md / Plan.md / the code. Suggested before the next
release.
