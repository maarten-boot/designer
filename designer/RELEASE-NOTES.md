# Release notes

## 0.3.0

Fixes to the model check and its type checker, and checks it was missing.

**The type checker**

- `abs(x) < value` no longer decides `x` is an integer before `value` has said
  anything: overloads are tried without side effects, and an ambiguous call
  waits for its context.
- `min(value, 1)` on a decimal type-checks: a literal takes the type the other
  arguments give it.
- `x in [1, 2]` with `x` a parameter type-checks: `x` takes the list's type.
- A rule is treated as reading the clock only when it calls `now`, `today` or
  `current` — `"now()"` inside a string is text.

**New checks**

- `MOD114`: a Type or Property naming a base type that does not exist.
- `MOD415`: a slot default of the wrong base type, or one its Type refuses,
  naming the rules that refuse it.
- `MOD416`: an override that points a reference slot at another entity.
- A Validator's own expression is checked whether or not anything uses it, and
  what is wrong with it is reported once, on the Validator, not at every use. A
  composite that does not parse is now reported at all.

Models that were clean stay clean; a model with any of the above now says so,
and the new errors block an export of a Schema that reaches them.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.3.0-py3-none-any.whl \
                                      designer_app-0.3.0-py3-none-any.whl

## 0.2.0

The same application and model as 0.1.0; what changed is the release itself.

- **The packages now say 0.2.0.** The first upload of this release carried
  files still numbered 0.1.0; they have been replaced.
- `make release` runs on a bare system Python, such as Debian's or Ubuntu's,
  which refuse `pip install` outside a virtual environment: it makes its own
  build environment in `~/.cache/designer-release/`.
- Nothing machine-specific is created inside the source tree any more, so the
  release can be built from a checkout shared between machines.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.2.0-py3-none-any.whl \
                                      designer_app-0.2.0-py3-none-any.whl

## 0.1.0 — first release

Designer is a desktop tool for authoring a data dictionary: validation rules,
type definitions, fields, record structures and the schemas that group them,
organised into contexts. This is its first installable release.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.1.0-py3-none-any.whl \
                                      designer_app-0.1.0-py3-none-any.whl

**Commands**

- `designer [model.json]` — the editor.
- `designer-check model.json [--level everything] [--json]` — the model check.
- `designer-export model.json SCHEMA [-o file.json]` — a Schema's export.

**What it does**

- Seven columns from what things are made of to what ships: Context, Validator,
  Interface, Type, Property, Entity, Schema. Every item kind is editable; one
  user action is one undo step; autosave with crash recovery.
- A model check of around ninety diagnostic codes, shown beside the field that
  caused each finding, with the ones that would block an export marked.
- 44 built-in validators, each shipped with passing and failing example values.
- Interfaces — how a value is written down and read back — with checks that a
  picture reads back every value its Type admits (INT202) and agrees with the
  Type's rules (INT401, INT402).
- **Schema export** (File ▸ Export Schema…): one self-contained JSON document
  per Schema, rules resolved along the Type chain and sorted into database
  checks and application rules, ready for a generator to translate.
- **The test bench** (Model ▸ Try a value…, Ctrl+T): type a value, see which of
  a Type's rules pass, and why; a runaway pattern is stopped after two seconds.
- Edit ▸ Preferences…, and deprecated built-ins marked and kept out of pickers.

**Known gaps** are listed in the specification, §16, and marked `[NOT BUILT]`
where each is specified. One design question is open: whether moving an item to
another Context should be refused when something would lose sight of it.

The file format is `schema_version` 1, or 2 for a model with Interfaces. 0.x
means the formats may still change; a change will be called out here.
