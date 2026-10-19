# Release notes

## 0.6.0

Small improvements to what the model check and the test bench say.

- **A composite rule without a message of its own now says something.** The
  test bench names the parts that failed for the value you tried; the export
  writes what the parts say together — all of an `AND`, any of an `OR`. Before,
  both were empty.
- **Cross-entity rules that read the clock** are no longer warned about
  (`MOD602`): the application enforces a rule across tables whatever it reads,
  so the warning only added noise. A file that marks such a rule for the
  database is now an error (`MOD605`), since only the application can enforce
  it.
- **A reference to an entity with no identity yet** (`MOD403`) is now reported
  as unfinished rather than wrong: the reference can be made first and the
  identity given after. It still blocks an export.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.6.0-py3-none-any.whl \
                                      designer_app-0.6.0-py3-none-any.whl

## 0.5.0

The second full crosscheck of code against documents, and what it found.

**Fixes you may notice**

- After an edit, the status line and the findings window no longer lose the
  whole-model findings — cycles, `INT202` and the like stay until the next full
  check, instead of vanishing.
- A settings file of the wrong shape no longer stops the application starting,
  and neither does a missing or unreadable model named on the command line:
  you get an empty model and a note.
- Loading a model refuses values it used to convert or crash on: `"abc"` as a
  decimal, `NaN`, a list written as a string, dates and times not written the
  one way the file writes them (`2026-08-29`, `14:30:00`).
- A date picture with an unquoted letter (`d-M-yyyy`) is refused instead of
  printing the letter; put literal text in quotes.

**New checks**

- `MOD417`: a rule given the wrong kind of argument for where it is bound — a
  slot on a Type rule, a path on an Entity rule, an empty path.
- `EXP305`: a regular expression that does not compile, with the reason.

**The type checker** now lets literals and open parameters take the type of
their context in lists (`value in [1.5, 2.5]` on a real), under `-`, in
`min`/`max` of literals alone, and beside a literal (`x * 2 < value` types `x`).
The test bench evaluates a fraction literal against a real as a real.

**A new example**, `examples/sales_broken.json`: a schema that will not export,
with a Fix for each cause.

Models that were clean stay clean. One that holds one of the values above no
longer loads, and says which value and why.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.5.0-py3-none-any.whl \
                                      designer_app-0.5.0-py3-none-any.whl

## 0.4.0

Smaller fixes, and remedies offered where a finding has one.

- **A Fix button in the findings window.** A finding with a one-step remedy
  offers it, named for what it does: *Add the missing referenced entities*
  (`MOD503`), *Add Customer to the schema* when a cross-entity path leaves it
  (`MOD509`), *Choose a Type that narrows Money* for a widening override
  (`MOD413`, only when such a Type exists). Each goes through the same prompt or
  dialog as the form's own button and is one undo step.
- **Grouping marks are checked for position** when typed values are read:
  `1,2,3` in a `#,##0.00` picture is refused instead of read as 123, and so is a
  mark after the decimal point. Leaving the marks out is still accepted. A
  picture that groups nothing (`0.00`) now refuses `1,234.00` rather than drop
  the comma.
- **Clearer messages:** `decimal(real)` says why it is refused, and comparing a
  decimal with the result of dividing two integers says where the real came
  from.

**Install** (Python 3.12+, tkinter — `python3-tk` on Debian and Ubuntu):

    python3 -m venv ~/.venvs/designer
    ~/.venvs/designer/bin/pip install designer_model-0.4.0-py3-none-any.whl \
                                      designer_app-0.4.0-py3-none-any.whl

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
