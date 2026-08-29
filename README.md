# Designer

A desktop tool for authoring a data model: validation rules, type definitions,
fields, record structures and the schemas that group them.

The specification and its three appendices are the source of truth. Every
non-obvious decision in this code is there, with the reasoning:

| Document | Covers |
|---|---|
| `designer-spec-v15.md` | the model, the application, packaging |
| `designer-signature-table.md` | expression types, operators, functions, `EXP` codes |
| `designer-validator-library.md` | the built-in Validators |
| `designer-diagnostics.md` | the diagnostic and consequence records |

## Layout

    packages/designer-model/    the domain: items, derivation, persistence,
                                diagnostics, the model check, the expression
                                checker, the built-in validators, commands,
                                undo and the session. Standard library only,
                                and it never imports tkinter.
    packages/designer-app/      the tkinter interface.
    examples/sales.json         the worked example, and the main test fixture.
    tools/build_stdlib.py       regenerates the built-in validator library.
    tools/build_matrix.py       regenerates the committed operator matrix.

## Status

**Phases 1a, 1b, 2 and 3a are done**: the package skeleton, the domain items, the
derived computations, load/save, the diagnostic records, the code registry, the
model check, the standard validator library, and the expression checker —
tokenizer and token map, composite parser, `ast` whitelist, signature tables,
type inference, and the `EXP` codes. Phase 3a adds the session layer the
interface will drive: commands and a bounded undo stack, the delete planner,
autosave with crash recovery, and application state.

Not yet built: the widgets (phase 3b) — the shell, the six columns, the
breadcrumb, the generated forms and the slot table.

## Working on it

    pip install pytest ruff
    PYTHONPATH=packages/designer-model/src:packages/designer-app/src pytest packages
    ruff format packages && ruff check packages

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

## The standard library

44 built-in validators, shipped as a JSON model fragment rather than as code, so
there is no second code path and the fragment exercises the file format for
real. Their UUIDs are derived, not assigned:

    uuid5(uuid5(NAMESPACE_DNS, "stdlib.designer"), canonical_name)

so `max_length` is `b5bfc6ca-...` on every installation, and a model file can
reference a built-in it does not contain. Regenerate with
`python3 tools/build_stdlib.py`.
