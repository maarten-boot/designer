# Designer

A desktop tool for authoring a data model: validation rules, type definitions,
fields, record structures and the schemas that group them.

The specification and its three appendices are the source of truth. Every
non-obvious decision in this code is there, with the reasoning:

`HISTORY.md` is every prompt in this project, in order — appended as each turn
arrives, attachments included, rather than reconstructed afterwards — the design decisions
as they were actually asked for, which is often more useful than the settled
answer in the specification.

| Document | Covers |
|---|---|
| `docs/designer-spec-v16.md` | the model, the application, packaging |
| `docs/designer-signature-table.md` | expression types, operators, functions, `EXP` codes |
| `docs/designer-validator-library.md` | the built-in Validators |
| `docs/designer-diagnostics.md` | the diagnostic and consequence records |
| `docs/designer-example-notes.md` | what the worked example exercises, and what it does not |
| `docs/designer-interfaces.md` | presentation and parsing |

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

## The columns

**Context, Validator, Type, Property, Entity, Schema** — strictly from what
things are made of to what ships. A Context scopes everything; a Validator
depends on nothing but the base types; a Type is built from Validators; a
Property is a Type given a name; an Entity is Properties given a shape; a Schema
is the deliverable. Beginning at the Schema would begin at the end.

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

Delete shows what it would do first: grouped by consequence rather than by
referencing item, with the destructive case — an entity losing everything it
inherits — called out, and the whole JSON subtree shown when a Context goes. No
delete is refused; it is one undo step either way.

Entities have an editable slot table: add value and reference slots, edit,
remove, reorder, and override an inherited one. Inherited slots are shown so the
effective record reads in one place, marked, and not removable — they are edited
on the entity that declares them.

Types and Entities have an editable rules table: add, edit and remove
validator bindings. A Type's rules apply to every value of that type; an
Entity's name the slot they apply to.

Schemas have an editable cross-entity rules table: anchor the rule on a member
and build each argument as a path.

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

    make deps      # pytest, ruff, mypy — floors, not pins
    make versions  # what the checks are actually running
    make check     # lint, types, tests, and the worked example
    make run       # open examples/sales.json
    make help      # the rest

The tool versions matter. `make check` passed here on mypy 2.3 while failing on
a user's mypy 1.9 with three errors I could not see — so the source avoids
syntax older tools cannot read (PEP 695 generics, notably) and annotates the
places where inference differs between versions. `make versions` prints what is
actually running.

`make check` is six nets and they catch different things. `lint` for style and
the constructs ruff knows are traps. `types` for attribute and call errors.
`test` for behaviour. `model` loads `examples/sales.json`, verifies it survives a
round trip, and runs the model check over it. `sync` asks whether the tests still call the code the way it is written — type
checking, so it needs no display. Changing a signature and updating only the
tests written beside it is the mistake that has reached the user most often, and
the widget tests skip on a machine without tkinter, so a green `make test` there
proves nothing about them. `docs` checks the specification and
its appendices against each other and against the code — section references,
diagnostic codes, the validator catalogue, file paths and the counts asserted in
prose. Its first run found seven errors, including a library that still said
"forty" after it grew to forty-four and a `build_example.py` that both the notes
and `make dist` named after it had ceased to exist, with the failure swallowed by
`2>/dev/null || true`. Prose goes stale the way code does; the difference is that
nothing runs it.

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

**Python 3.12 is the floor**, declared once in each `pyproject.toml` and nowhere
else — ruff infers its target from `requires-python`, and mypy is told the same.

The three agreeing matters more than the number. When they did not — the floor
at 3.14 while development ran on 3.12 — ruff correctly applied PEP 758 and
rewrote `except (A, B):` to `except A, B:`, which 3.14 accepts and 3.12 rejects,
and the build broke. Raise `requires-python` only when the interpreter in use
has moved too.

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

## Column widths

A column asks for three quarters of its widest row — the longest name is usually
an outlier — and that one number is both its starting width and its minimum.

An earlier version had two numbers, a preferred width with a flat
ten-character floor under it, and it was wrong in both directions: the floor
swallowed the calculation for every column of short names, so they all came out
identical, and the ceiling was fixed without reference to how many columns
there are, so adding a seventh pushed the total past the screen it was meant to
fit. The ceiling is now derived from the column count.

Each column's scrollbar is packed *before* its list. Packed after, it is the one
the packer squeezes to nothing when the column gets narrow — which is exactly
when it is needed.

## Sorting

Every browser column is alphabetical and case-insensitive, and its heading
toggles the direction — a long list is worth reversing rather than scrolling to
the end of. The direction is remembered per column.

Reversing a tree sorts the siblings at each level; it does not turn the tree
upside down, which would put children before their parents and break the
single-pass insert. Built-in validators stay after the authored ones either way:
that is a grouping, not a sort key. Slots are the exception that is never
sorted — their order is stored, it is what the Up and Down buttons change, and
it survives to the generated table.

## The breadcrumb

Text, and nothing else: `Context:  common › sales`. It is not decoration — the
active Context filters every column and decides where a new item is created, so
with the Context column collapsed it is the only indicator of both. But saying
where you are and being a way to move are different jobs, and the Context column
already does the second. The clickable ancestors and the dropdown on the last
segment are gone: a label that looks like a control is worse than either.

## Which selection is current

Several columns hold a selection at once, and the editor shows one of them: the
one chosen **most recently**, not the rightmost. The columns run from primitives
to deliverable, so choosing a Type after a Property would otherwise leave the
Property in the form and nothing would appear to have happened.

The active column's selection is amber; the others keep a muted grey, so an
earlier choice still reads as chosen without competing with the current one. A
selection made in code — the context chosen at startup — goes through the same
path as a click, or it would be selected without being current. Clicking a row
that is *already* selected is handled separately: it changes nothing in the
widget, so no select event fires.

## Highlighting, not filtering

One thing filters: the active **Context**, because an item outside it is not
merely unrelated but unreachable. Everything else highlights, and scrolls the
related row into view.

Two filters were built and removed. A follow-selection toggle turning highlights
into filters reduced a fourteen-row Type column to the one row it had already
highlighted. And a schema selection narrowing the Entity column to its members
hid exactly the entities somebody adding one is looking for. In both cases the
highlight already said everything the filter did, while taking away what you
might compare against or switch to.

## Findings

**Model ▸ Check model and list findings…**, or F5, or click the status line.
The status line names the counts and says how many would block an export; the
window says which, about what, and in words. Double-clicking a finding takes the
selection to the item — including its context, since the item may well be
somewhere the columns are not currently looking.

A list left open follows the model rather than going stale.

**View ▸ Findings shown** sets how much appears: errors only, warnings and
errors (the default), unfinished items too, or everything including notes. The
default is warnings because a model under construction is full of unfinished
items and unreferenced types — every new type is referenced by nothing until
something references it — and a list that is mostly noise trains people to
ignore it.

Whatever is filtered out is counted in the status line, and anything that would
block an export is named at every level. Those are mostly `incomplete` findings,
which a low level hides — so without that rule a model could reach an export
with a fault nobody had been shown. `tools/check_model.py --level` takes the
same four values.

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

## Slots

The rules live in `slots.py`, tkinter-free: an override must narrow and may not
make a required slot optional or change its kind; a required reference cannot be
set null when its target goes; a default is read as the slot's base type, so
`0.10` on a decimal stays exact. They are checked before anything happens, so a
refusal names the mistake rather than turning up later as a finding.

The override picker offers only Types that narrow the inherited one, so a
widening override cannot be built and then refused. Reference targets are
restricted to concrete entities with an identity — an abstract one has no table
to point at, and one without an identity has no column to point at.

## Rules

The rule dialog asks for what the rule needs, and nothing else. Which arguments
appear and what each expects is *inferred*, not declared: `check_leaf` runs the
validator's own expression against the value it will be given, so `between` on a
Money type asks for two decimals and the same rule on a date asks for two dates.
Change the rule, or the slot it applies to, and the boxes are rebuilt.

A validator's form separates **how the rule is used** from **how it is built**.
`is_country_code` is used as `is_country_code`; its implementation is
`regex_full_match(value, "[A-Z]{2}")`. The two look alike for `ends_with`,
whose implementation calls the function of the same name — and that coincidence
is what made showing only the expression misleading.

Five expression functions return a verdict and are therefore available as rules
already: `contains`, `ends_with`, `starts_with`, `is_finite`, and
`regex_full_match` as **`matches(pattern)`**. The other two dozen (`len`,
`scale`, `lower`, `abs`, the duration constructors…) return a length or a
number or a string rather than a yes or no, so they cannot be a rule on their
own; they are used inside an expression. Each built-in that exposes a function
names it, since the same function is available for a rule of your own.

A validator's form says which base types it takes — `string` for `max_length`,
`integer, real, decimal` for `non_negative`, `any base type` for `equals`. It is
**derived from the expression, never declared**: a validator does not have *a*
base type, and a field to pick one would either throw that polymorphism away or
restate what the expression already decides and then drift from it.

A rule that combines other rules is a **composite** Validator, not something
expressed in the binding. Set Kind to composite and write the operands by name:

    (is_email AND non_blank OR is_uuid) OR (NOT is_blank)

`AND`, `OR`, `XOR`, `NOT` and parentheses, with `AND` binding tighter than `OR`.
Every operand is applied to the same value. The file holds identities and the
form shows names, so renaming a rule cannot break an expression that uses it —
and changing the Kind translates the expression rather than leaving names where
identities belong.

Rules that cannot apply are not offered at all. `max_length` does not appear for
a decimal — the alternative is offering it and then reporting an error the user
could not have avoided. While a type is unfinished everything is offered, since
nothing is known to contradict.

## Paths

A cross-entity rule reaches a value by walking reference slots from one member
of a Schema. The picker offers one step at a time and offers only steps that
keep the path legal, so an invalid path cannot be built: a reference leaving the
Schema is absent, references stop being offered at the fourth segment, and a
value slot ends the walk. That is the difference between a control that guides
and one that grades — the model check still runs, because a file can arrive from
anywhere.

Changing the anchor clears the paths: a route is meaningless without the entity
it starts from. And `value` is one of the paths to build, not a given — a rule
spanning entities has to say *which* value before it can say anything about it,
and that choice decides the types the other arguments need.

Enforcement is not offered as a choice. A rule spanning two tables cannot be a
check constraint whatever anyone claims, so a field to claim it would only be a
way to be wrong.

## Tables in the form

Every table sorts on a heading click, and the slots table needs care because its
stored order is the column order of the generated table. So a sort is a **view**:
while one is applied, Up and Down are disabled, because a control that moves a
row somewhere the eye cannot follow is worse than no control. A third click on
the same heading returns to stored order and gives them back.

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
copy it into the model. Copying leaves the built-in list showing: the copy does
not replace the original, and every rule already bound to it keeps using it.
What changes is that the *name* now resolves to the copy in that context and
below — which both forms say in amber, the copy naming what it takes precedence
over and the built-in naming where it has been taken over. It used to report the item as *gone*, because built-ins
are global and never written to the model file — only references to them are —
so looking one up in the model found nothing. The item was there; it simply
could not be edited.

## Interfaces

An `Interface` says how a value of some base type is written down for a person
and read back. A Type binds any number of them, at most one default, and a Type
that binds none uses the nearest ancestor's — deepest wins, and `effective_interface`
reports *where it came from* as well as what it is. A presentation that looks
declared when it was inherited is worse than no inheritance: somebody edits it
and silently creates a binding where there was none.

The document declares the lowest version that can represent it. A model with no
Interfaces stays at `schema_version` 1, keeps loading in an older build, and
round-trips byte for byte — and a version 1 document carries no version 2 keys,
because the shape has to follow the declared version or the file is lying about
itself.

Deleting an Interface is never refused. Each affected Type falls back along its
chain, and the impact dialog says the outcome rather than the mechanism —
"PositiveMoney will present with money_uk, from Money", or "no presentation will
remain". A Type without one is an ordinary state, not a fault.

**Context · Validator · Interface · Type · Property · Entity · Schema** — seven
columns, still 560px at their minimum. The Interface form previews the picture
against sample values and says when they do not read back; a Type says what it
presents with and, when that was inherited, names the ancestor it came from with
an action to override it here.

## Pictures

`designer_model/pictures.py` presents a value for a person and reads one back.
It is domain code, not interface code: the export carries pictures, so a
generator needs them without needing a window.

A picture never decides whether a value is *allowed* — that is a Validator, and
it runs after parsing and before presenting. `X(30)` is a hint about width, not
a limit; a longer value presents in full and the application scrolls.

Numbers carry two separator settings, and the picture stays canonical: `#,##0.00`
with a comma decimal and a full-stop grouping presents `1.234.567,50`. Writing
the separators into the picture was rejected — with only one of them present,
`#,##0` and `0,00` are indistinguishable. Dates need no such setting, because
there the separator is literal text and a region simply writes `dd/MM/yyyy`.

The law is `parse(present(v)) == v` for every value the Type admits, and
`check_round_trip` is that law as a function. The quantifier matters: `X(3)U` is
sound on a Type with `is_uppercase` and lossy without it, and `#,##0.00` is
sound with `max_scale(2)` and rounds without it. Neither the picture nor the
rules are at fault in those pairs — the pair is.

## The standard library

44 built-in validators, shipped as a JSON model fragment rather than as code, so
there is no second code path and the fragment exercises the file format for
real. Their UUIDs are derived, not assigned:

    uuid5(uuid5(NAMESPACE_DNS, "stdlib.designer"), canonical_name)

so `max_length` is `b5bfc6ca-...` on every installation, and a model file can
reference a built-in it does not contain. Regenerate with
`python3 tools/build_stdlib.py`.
