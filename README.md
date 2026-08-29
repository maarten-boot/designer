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

    packages/designer-model/    the domain: items, derivation, persistence.
                                Standard library only. Never imports tkinter.
    packages/designer-app/      the tkinter interface.
    examples/sales.json         the worked example, and the main test fixture.

## Status

**Phase 1a is done**: the package skeleton, the domain items, the derived
computations, and load/save.

Not yet built: the model check and diagnostics (1b), the expression checker and
standard library (2), the interface (3+).

## Working on it

    pip install pytest ruff
    PYTHONPATH=packages/designer-model/src:packages/designer-app/src pytest packages
    ruff format packages && ruff check packages

`pyproject.toml` requires Python 3.14. The code avoids syntax newer than 3.12 so
it can be exercised on older interpreters during development.

## The acceptance test

`test_round_trip_is_byte_identical` loads `examples/sales.json`, saves it, and
compares the text. It exercises nullable references, the typed literal envelope,
composite expressions holding operand UUIDs, binding UUIDs, slot overrides and
stored paths in one assertion — which is why the example was written before any
of this code.
