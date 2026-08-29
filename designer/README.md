# Designer

A desktop tool for authoring a data model: validation rules, type definitions,
fields, record structures and the schemas that group them.

The specification and its three appendices are the source of truth. Every
non-obvious decision in this code is there, with the reasoning:

| Document | Covers |
|---|---|
| `docs/designer-spec-v15.md` | the model, the application, packaging |
| `docs/designer-signature-table.md` | expression types, operators, functions, `EXP` codes |
| `docs/designer-validator-library.md` | the built-in Validators |
| `docs/designer-diagnostics.md` | the diagnostic and consequence records |
| `docs/designer-example-notes.md` | what the worked example exercises, and what it does not |

## Layout

    packages/designer-model/    the domain: items, derivation, persistence,
                                diagnostics, the model check, the expression
                                checker, the built-in validators, commands,
                                undo and the session. Standard library only,
                                and it never imports tkinter.
    packages/designer-app/      the interface. rows.py, selection.py and
                                state.py are deliberately tkinter-free and
                                carry the logic worth testing; the widget
                                modules are thin adapters over them.
    examples/sales.json         the worked example, and the main test fixture.
    tools/build_stdlib.py       regenerates the built-in validator library.
    tools/build_matrix.py       regenerates the committed operator matrix.

## Status

**Phases 1a, 1b, 2, 3a and the first round of 3b are done**: the package skeleton, the domain items, the
derived computations, load/save, the diagnostic records, the code registry, the
model check, the standard validator library, and the expression checker —
tokenizer and token map, composite parser, `ast` whitelist, signature tables,
type inference, and the `EXP` codes. Phase 3a adds the session layer the
interface will drive: commands and a bounded undo stack, the delete planner,
autosave with crash recovery, and application state.

Round one of 3b adds the shell: the window, the menu bar, the six columns with
filters, the breadcrumb, manual column collapse, and the status line. Round two
adds the editor: a generated form per kind, live editing through the undo stack,
findings shown beside the field that caused them, and New and Duplicate.

Schema membership is editable: add, remove, and add-missing-referenced-entities,
each a single undo step. Adding one entity names the cascade before it happens —
adding `OrderLine` to an empty schema pulls in `Order` and `Customer`, and says
so first.

Not yet built: the slot table, cross-entity rules, and Delete with its impact
dialog. Those are still read-only summaries.

`mypy.ini` is a narrow net rather than a typing campaign: attribute and call
errors only, with the noisy rules switched off. It exists because four bugs
reached the user through one hole — an edit that silently changed nothing,
leaving a reference to something no longer there. `Focus.members`,
`_editor_note`, a changed signature, an import already rewritten. Each is
invisible to a test suite whose widget half skips without a display, and each is
caught by this. Run it before believing a green suite.

**The widget layer has not been run.** It was written on a machine with no
tkinter and no display: the logic underneath it is tested, the widgets are not.
Expect to find things.

## Working on it

    make deps      # pytest, ruff, mypy
    make check     # lint, types, tests, and the worked example
    make run       # open examples/sales.json
    make help      # the rest

`make check` is four nets and they catch different things. `lint` for style and
the constructs ruff knows are traps. `types` for attribute and call errors.
`test` for behaviour. `model` loads `examples/sales.json`, verifies it survives a
round trip, and runs the model check over it.

The third of those lies most easily. On a machine without tkinter every widget
test skips and the suite still reports success, so `make types` is not optional
there — it is the net that catches a reference to something that no longer
exists.

`packages/designer-app/tests/test_widgets.py` builds a real window: it skips
without tkinter or a display, and does the work where there is one. Run it after
touching anything in the interface —

    PYTHONPATH=packages/designer-model/src:packages/designer-app/src \
      pytest packages/designer-app/tests/test_widgets.py -v

It clicks every entry in the menu bar with the dialogs stubbed, collapses and
restores every column, and drives selection through each list. That is how the
reset-layout crash should have been found.

`pyproject.toml` requires Python 3.14, but ruff's `target-version` is pinned to
`py312` so the source stays runnable on older interpreters during development.
That pin is load-bearing: left to infer from `requires-python`, ruff applies
PEP 758 and rewrites `except (A, B):` to `except A, B:`, which 3.14 accepts and
3.12 rejects.

## Two acceptance tests

Both were written before the code they check, which is why they are worth
something.

**1a.** `test_round_trip_is_byte_identical` loads `examples/sales.json`, saves
it, and compares the text. One assertion exercises nullable references, the
typed literal envelope, composite expressions holding operand UUIDs, binding
UUIDs, slot overrides and stored paths.

**1b.** `test_example_produces_exactly_the_baseline` asserts the example yields
three findings and no more — `MOD602`, `MOD101`, `MOD601` — and the surrounding
tests pin the codes that a prototype checker, written against the specification
documents rather than against this code, produced for four deliberately broken
variants.

## Running it

    pip install -e packages/designer-model -e packages/designer-app
    designer examples/sales.json

or without installing:

    PYTHONPATH=packages/designer-model/src:packages/designer-app/src \
      python3 -m designer_app.main examples/sales.json

tkinter is standard library but packaged separately on Debian and Ubuntu
(`python3-tk`); the app checks and says so rather than throwing an ImportError.

## The editor

The editor scrolls: an entity with a dozen slots and a handful of rules is
taller than the pane, and the bottom would otherwise be unreachable. The
scrollbar appears only when there is something to scroll, and a new form starts
at its beginning rather than wherever the previous one was left.

The editor is live. There is no Apply: a structured control commits the moment
it changes, a text field commits when it loses focus or takes Enter, and Escape
puts a field back. That follows from one user action being one undo step — an
Apply button would either bundle a form's worth of edits into one step or push
several at once, and neither is what Ctrl-Z should mean.

Every form names the context the item lives in, read-only: an item is moved by
changing its context, not from the form. The breadcrumb and the form share one
path helper, so the two cannot disagree about where something sits.

`forms.py` decides what a form contains and `formview.py` renders it. So which
Types may be a parent, which choices would create a cycle, and where a finding
attaches are all settled in tests rather than by looking at a window.

Two hazards live here, both found by the widget suite rather than by reading.
A `StringVar` left as a local is garbage collected — Tk holds it by Tcl name,
not by reference — after which the entry reads back an empty string and commits
it as a cleared field. Every field variable is kept alive deliberately.

An edit belongs to the item the form was **built for**, not to whatever is
selected when the commit arrives. Rebuilding a form destroys its widgets, and a
widget being destroyed fires `<FocusOut>`; the commit that fires can land after
the selection has already moved on. Carrying the item's identity on the form is
what stops an edit from reaching the wrong item.

Two things the split makes easy to get right. A composite validator shows
operand *names* while the file holds identities, so renaming a validator cannot
break an expression that uses it — and a test asserts the round trip is exact. A
Type is never offered its own descendants as a parent, so a cycle cannot be
built and then complained about.

## Tables in the form

A table field carries its rows and its buttons as data, so which entities may
join a schema, which button is enabled, and what an addition would pull in are
all decided in `forms.py` and `designer_model/membership.py` — both testable
without a display. The widget draws rows and wires buttons.

Declining the cascade adds the entity you asked for and leaves the schema
unclosed, rather than cancelling the addition. Refusing the whole thing would
make closure compulsory by the back door, and closure is a warning, not a rule.

Membership planning mirrors deletion: one walk produces both what the dialog
shows and the command that carries it out, so the two cannot disagree. An entity
that cannot join says why — a sibling context is out of reach, and the fix for
that is a modelling one no dialog can make.

## The session

`designer_model.session.Session` is what the interface drives, and it holds no
interface: the document, the undo stack, the dirty flag, autosave, and the
findings. That placement is deliberate — a command-line tool or a generator
wants the same undo and recovery guarantees, and a session that needs a window
could not be tested.

The unit of undo is **one user action**, not one object. Editing three slot rows
is three steps; a delete with a dozen fixups is one, because a Ctrl-Z that
restored an entity while leaving its references broken would be worse than
either state. `plan_delete` walks the model once and returns both the
consequences the dialog shows and the command that carries them out, so the two
cannot drift apart.

## The expression checker

Everything that looks inside an expression goes through
`designer_model.expressions`, and nothing else in the codebase calls `eval` or
`compile`. Three pieces share one `ast` walk:

- the **whitelist** that makes `eval` defensible — attribute access is banned
  outright, which is why the string operations are free functions;
- **type inference**, which resolves parameters by unification rather than
  annotation: from `min <= value <= max` with a date value, both bounds resolve
  to date;
- **determinism**, derived from whether the clock is read, which decides whether
  a rule can ever be a check constraint.

`tests/operator_matrix.txt` is the full type matrix for every binary operator,
committed so a change to the signature tables appears as a diff and an
unconsidered pair shows as an explicit `-` rather than hiding.

Base types and built-in validators are both selectable and both read-only, and
each says why. A base type also lists the Types that narrow it directly and the
ones whose chain ends at it. Neither is in the model file — a Type refers to a
base type by name, and only references to built-ins are stored — which is why
looking either up in the document finds nothing.

Selecting a built-in shows it read-only, with a note saying so and a button to
copy it into the model. It used to report the item as *gone*, because built-ins
are global and never written to the model file — only references to them are —
so looking one up in the model found nothing. The item was there; it simply
could not be edited.

## The standard library

44 built-in validators, shipped as a JSON model fragment rather than as code, so
there is no second code path and the fragment exercises the file format for
real. Their UUIDs are derived, not assigned:

    uuid5(uuid5(NAMESPACE_DNS, "stdlib.designer"), canonical_name)

so `max_length` is `b5bfc6ca-...` on every installation, and a model file can
reference a built-in it does not contain. Regenerate with
`python3 tools/build_stdlib.py`.
