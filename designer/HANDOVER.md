# Designer — handover

For whoever picks this up next, including a later me. Written 30 August 2026,
after 95 turns; housekeeping pass 17 October 2026.

The state is easy to establish (`make check`), so this is mostly about the
things a fresh reader would otherwise have to rediscover: what has already been
decided, what keeps going wrong, and what to do next.

---

## What it is

A desktop tkinter tool for authoring data models. Contexts scope everything;
Validators are rules; Interfaces say how a value is written and read back;
Types combine a base type with rules and a presentation; Properties name a
Type; Entities are slots; Schemas gather Entities for export to a relational
store.

Seven columns, left to right, strictly from what things are made of to what
ships:

    Context · Validator · Interface · Type · Property · Entity · Schema

Two packages. `designer-model` is the domain: items, derivation, persistence,
diagnostics, the model check, the expression checker, pictures, commands, undo,
session. Standard library only, and it never imports tkinter. `designer-app` is
the interface, with `rows.py`, `selection.py`, `state.py`, `slots.py`,
`bindings.py`, `paths.py`, `forms.py`, `impact.py`, `findings.py`, `factory.py`,
`exporting.py`, `testbench.py` and `preferences.py` deliberately tkinter-free so
the logic worth testing can be tested without a display.

---

## Where things stand

`xvfb-run -a make check` green on 17 October: 1059 tests, none skipped, after
the crosscheck that evening. Re-run it rather than trusting
the number. The machine has pip, tkinter and Xvfb but no system-wide ruff, mypy
or pytest, so put them in a virtual environment and its `bin` first on `PATH`.
Without `xvfb-run` the widget suite skips and `make check` still says green.

Almost everything in the specification is built and editable — `INT202` by
sampling (`pictures.PROBES`, appendix *interfaces* §7.3), with the project's
first evaluator, `expressions/evaluate.py`. What is not is listed in spec §16
and marked `[NOT BUILT]` where it is specified; the crosscheck of 17 October
(turn 139) found it. One question there is still the user's to answer: refusing a
Context move or allowing and reporting it (spec §10.1). Shadowing a built-in was
decided in turn 144 — a note, as built.

**Done, with what is worth knowing:**

1. **Schema export is done.** `designer_model/export.py`,
   **File ▸ Export Schema…** via `designer_app/exporting.py`,
   `tools/export_schema.py`, `make export`, with every decision in spec §9.6.
   `examples/sales_schema.export.json` is its acceptance test, compared byte
   for byte. **No YAML** — dropped in turn 138: an external tool converts the
   JSON, so do not build a serialiser.
2. **Phase 4 is done.** Deprecated built-ins: `data/deprecations.json` beside
   the library (not inside it — the library must stay an ordinary model
   document that round-trips), `Library.offered()` for pickers,
   `Library.advice()` for the form and `LIB102`. To deprecate one, add it to
   `DEPRECATED` in `tools/build_stdlib.py`, bump `LIBRARY_VERSION`, and run
   `make dist`. Preferences are built
   (`designer_app/preferences.py`, `PreferencesDialog`). The test bench
   is built (`designer_model/bench.py`, `designer_app/testbench.py`,
   `TestBenchWindow` in `dialogs.py`); it judges in a subprocess so a runaway
   regex is killed after `bench.TIMEOUT`.

---

## What the user is doing right now

Building a real model with the tool and reporting what breaks. That has been
far more productive than building features: the last dozen turns were all their
findings, and several were categories of failure rather than single bugs.

**Their reports are the best input this project gets.** Quoting an exact
message has twice shown that the message itself was the defect, not the model.

---

## Decisions already made — do not relitigate without asking

- Items are created **empty**; incomplete is a legal state and saving is always
  allowed. The model check reports incompleteness; the interface does not
  refuse it.
- **No delete is refused.** An impact dialog names consequences, and undo
  covers the rest.
- One user action is **one undo step**. `Macro` bundles multi-object changes.
- Expressions are stored as source, with composite operand UUIDs in the text.
- The Context filters; **everything else highlights**. Filtering hid exactly
  the rows somebody was looking for.
- A Validator does **not** have one base type. `max_length` takes string,
  `equals` takes all eight. Accepted types are derived from the expression,
  never declared.
- An Interface presents and parses; it **never** decides whether a value is
  allowed. `X(30)` is a width hint, not a limit. Anything that constrains is a
  rule.
- Pictures stay canonical (`.` decimal, `,` grouping) with two separator fields,
  so one picture serves every region.
- A document declares the **lowest** `schema_version` that can represent it, and
  carries no keys from a later version.
- Cross-entity rules are always enforced in the application. A rule spanning two
  tables cannot be a check constraint.
- Extension is **flattened**: one table per concrete entity, no shared base. So
  a reference to an entity with concrete descendants reaches only its own rows
  (`MOD404`), and slot narrowing is legal precisely because tables are flat.

---

## How to work here

    make deps       # floors, not pins
    make versions   # what the checks are actually running
    make check      # lint, types, sync, test, model, docs
    make run        # open examples/sales.json
    make export     # export sales_schema to standard output
    make run EXAMPLE=../sales.json    # the user's own working model

`make check` is six nets:

| target | catches |
|---|---|
| `lint` | ruff, including duplicate test names |
| `types` | mypy over the source, `attr-defined` enabled |
| `sync` | mypy over the **tests** — `call-arg` only. Signature drift. |
| `test` | behaviour |
| `model` | the worked example round-trips and carries its three findings |
| `docs` | the documents against each other and against the code |

**Releasing** (decided in turn 146: GitHub releases, MIT, semver from 0.1.0):

1. Bump `version` in both `packages/*/pyproject.toml` and the
   `designer-model==` pin in designer-app's; a test fails if the three disagree.
2. `xvfb-run -a make check`, then `make release` — it builds into `dist/` and
   verifies the wheels in a clean environment. It runs on a bare system Python:
   without `build` it makes an environment for it in
   `~/.cache/designer-release/<python version>` (turns 148 and 151).
3. The user tags and publishes: `git tag -a vX.Y.Z -m "Designer X.Y.Z"`,
   `git push origin vX.Y.Z`, then a GitHub release from the tag with the four
   files in `dist/` attached and `RELEASE-NOTES.md`'s section as its text.
   **Check the file names in `dist/` carry the tag's version** before
   publishing: v0.2.0 first went out with packages still numbered 0.1.0,
   because the tag moved and the pyproject versions did not (turn 153).

Tagging and publishing are outward-facing: prepare them, and leave them to the
user unless asked. A package that has not been installed somewhere clean and run
has not been verified — which is what `make release` does.

---

## The standing instruction

**Every prompt the user sends goes into `HISTORY.md`, attachments included, as
part of the turn it arrives in.** It was asked for twice because it lapsed
twice. Appending is not a tidy-up for later; the file is wrong the moment a turn
is answered without it. `make docs` checks the numbering is contiguous, which
catches a botched append but cannot catch a forgotten one.

Their saved preference is the other standing instruction: when changing code,
cross-check the *existing* tests for that code, not only the ones written
alongside the change.

---

## What keeps going wrong

Read this part. Every item is a mistake made more than once.

**The widget tests skip without a display.** For most of this project they
never ran where the code was written, and `make test` green said nothing about
`test_widgets.py`. They run now — `xvfb-run -a make check` — so use it; a plain
`make check` still skips them silently. Four separate
failures reached the user this way. Two defences exist — `make sync` type-checks
the tests, and logic gets extracted into tkinter-free modules so it can be
tested for real — but neither is complete. When touching a widget test, reason
about its premises explicitly and verify them headlessly.

**Changing behaviour and updating only the nearby tests.** Removing the refusal
popups broke three older tests covering the same paths. Adding the slot-name
pre-fill invalidated a test written one turn earlier. Search the suite for the
behaviour, not the function name.

**Display strings are not identities.** `str(subject)` shortens a uuid to eight
characters; every entity in a hand-numbered model begins `e0000000`. Building
row ids from it made the findings window refuse to open.

**tkinter owns some attribute names.** `self._name = tk.StringVar(...)` broke
`destroy()` on every dialog. There is a static guard now.

**A finding's message is not its title.** The form showed code titles and threw
away the rendered message, which already carried every detail the reader needed.
Several messages have since been rewritten to name both sides of a comparison —
`MOD413` names the chosen and inherited types, `MOD404` names what extends the
target. When a user asks what a message means, the message is usually the bug.

**Stored fields with no editor.** Identity, then indexes, then default order:
each stored, persisted and checked, with no control anywhere, so the model check
could report a fault the interface offered no way to fix. There is now a test
that walks every stored field of every item kind and asserts it is reachable
from a form. It was verified against all three.

**Prose goes stale the way code does.** `make docs` exists because the spec
still described a clickable breadcrumb that had been removed, a validator
library that said "forty" after it grew to forty-four, and a `build_example.py`
that `make dist` called with the failure swallowed. Note its limit: it checks
that a cited diagnostic code *exists*, not that it means what the sentence says.
A wrong-but-real code number got through and had to be caught by reading.

**Nothing machine-specific inside the repository.** The working tree is an NFS
share used from more than one machine. A virtual environment made in it here
(Python 3.14, copied binaries) was found and run by the user's host on 3.12 and
failed with "Text file busy". Environments go in the machine's own cache or a
temporary folder, never in the tree.

**Tool versions must be pinned enough to agree.** `make check` passed here on
mypy 2.3 and failed for the user on 1.9. The source now avoids syntax older
tools cannot read.

---

## Documents

All in `docs/`, all checked by `make docs`.

| file | covers |
|---|---|
| `designer-spec-v16.md` | the model, the application, packaging |
| `designer-signature-table.md` | operator and function types |
| `designer-validator-library.md` | the 44 built-ins |
| `designer-diagnostics.md` | diagnostic and consequence records |
| `designer-example-notes.md` | what the worked example exercises |
| `designer-interfaces.md` | presentation and parsing |

Revision 16 was the first made *while building*, and every change in it came
from using the tool rather than reading the document. Changes are marked
`[CHANGED]` where they sit, with what they replaced.

`HISTORY.md` is every prompt in order. Turns 1–27 are verbatim from a session
transcript; the rest are reconstructed from the live conversation and are
faithful in substance, with the longer ones possibly differing slightly in
wording. The distinction is stated in the file.

---

## Setting up a fresh machine

The project lives in git now; the zip-only container of the early sessions is
gone. The user's own working model is `sales.json` at the repository root,
next to this `designer/` directory; `examples/sales.json` is the fixture.

    make deps       # needs pip; ruff, mypy and pytest
    make check

The GUI and `test_widgets.py` also need tkinter (`python3-tk` on Debian and
Ubuntu) and a display.

Edit with exact replacements that must match once and fail loudly otherwise. A
patch that silently does nothing is worse than one that fails, because the run
continues and the change is simply absent.
