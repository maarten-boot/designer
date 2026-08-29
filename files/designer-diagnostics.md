# Designer — The Diagnostic Object

29 August 2026. **Accepted in full.** An appendix to the main specification,
authoritative for §11.6 and for the impact dialog's record in §11.1.

---

## 1. What it has to serve

Five consumers, and the record has to satisfy all of them without becoming a
union of their needs:

| Consumer | Needs |
|---|---|
| **Model check list** (§13.10) | flat, filterable by severity and kind, sortable, click-to-navigate |
| **Inline binding feedback** (§13.6) | findings for *one binding row*, rendered beside it as it is edited |
| **Expression editor** (§13.6) | a character span to underline in the `Text` widget |
| **Export gate** (§3.1, §9.2) | machine-readable "does this block export" |
| **Tests** (§14.2) | assert an expected code, not an expected sentence |

One thing it does **not** serve. The delete impact dialog (§11.1) predicts what
*would* happen if the user proceeds; a diagnostic describes what *is* true now.
Forcing both into one record means a "hypothetical" flag and a "consequence"
field that findings never populate. They get separate records — but they **share
the locator** (§3), because both need to say "the third slot of this Entity".
Share the part that is genuinely common, not the shape.

---

## 2. The record

```python
@dataclass(frozen=True, slots=True)
class Diagnostic:
    code:     str                        # "EXP201" — into the registry (§8)
    subject:  Subject                    # what it is about (§3)
    span:     TextSpan | None = None     # where inside an expression (§4)
    args:     Mapping[str, ArgValue] = {}    # message substitution (§5)
    related:  tuple[Related, ...] = ()   # other items involved (§6)
    fix:      FixHint | None = None      # a one-command remedy, if there is one (§7)
```

Note what is **absent**: no severity, no message, no title. Those belong to the
*code*, not to the instance (§5). A code that reports as an error in one place and
a warning in another is a bug waiting to be argued about, and putting severity on
the instance makes that bug expressible.

Also absent: any item *name*. Names are resolved at render time (§5), because a
diagnostic can outlive the name it was created with.

---

## 3. Subject — the shared locator

```python
@dataclass(frozen=True, slots=True)
class Subject:
    item_uuid: UUID
    item_kind: Kind                 # denormalised, so a list renders without lookups
    path:      tuple[Step, ...] = ()    # where inside the item
```

A `Step` is `(field: str, key: UUID | str | None)`:

```
()                                                  the item itself
(("expression", None),)                             its expression
(("slots", <slot-uuid>), ("type_override", None))   one slot's override
(("validators", <binding-uuid>),
 ("arguments", "max"))                              one argument of one binding
```

**List elements are addressed by UUID, never by index.** An index goes stale the
moment a list is reordered or an earlier element is removed, and the model check
runs asynchronously with editing (§9) — so a finding created against
`slots[2]` can point at the wrong slot by the time the user clicks it. A UUID
cannot drift.

That has a consequence for the specification: **bindings must carry a UUID.**
Slots already do (§12 stores paths as lists of slot UUIDs), but §5.6 defines a
binding with no identity of its own. It needs one — for this locator, for the
impact dialog to name a removed binding (§11.1), and for the inline feedback to
match findings to the row it is drawing.

`item_kind` is denormalised deliberately. The model check list renders hundreds
of rows with an icon and a kind label; making each one resolve its item first
turns a cheap list into a lookup storm.

---

## 4. Spans, and the two coordinate systems

```python
@dataclass(frozen=True, slots=True)
class TextSpan:
    start: int      # character offset, stored form
    end:   int
```

Offsets are in the **stored** text, which is the canonical form: it matches the
file, the JSON tab, and any CLI report.

For a **leaf** expression that is the whole story — nothing is substituted, so
stored and displayed text are identical.

For a **composite**, they are not. Operands are stored as UUIDs and displayed as
names (§5.2), so offset 14 in the stored text is not offset 14 on screen. The
resolution is cheap because the substitution pass already walks tokens: the
tokenizer returns a **token map**, a list of `(stored_span, display_span)` pairs,
alongside the display text. The editor translates through it; nobody else needs
to.

The alternative — reporting a token index instead of a character offset — was
tempting and rejected. It would make the span meaningless to a CLI or a test that
never tokenises, and it would put the burden on every consumer rather than the
one that has the problem.

---

## 5. Messages come from the code registry

```python
@dataclass(frozen=True, slots=True)
class CodeDefinition:
    code:          str
    severity:      Severity          # error | warning | incomplete | info
    title:         str               # short, for a list column: "Type mismatch"
    template:      str               # "{left} and {right} cannot be combined — …"
    scope:         Scope             # item | context | model  (§9)
    blocks_export: bool = False
```

The registry is a module of pure data, like the signature table. Three things
follow from putting the human-facing text here rather than on the instance:

- **Wording is consistent** across every occurrence of a code, and changing it is
  one edit.
- **Tests assert codes**, not sentences, so rewording a message never breaks a
  test — which is what makes the library self-test (§14.2) durable.
- **Translation later is a second registry**, not a hunt through the code.

`blocks_export` is where the "incomplete blocks export" rule and "closure is
required for export" (§9.2) live *declaratively*, instead of as a list of special
cases inside a future exporter. Note this is why severity can stay fixed per code:
the Schema-not-closed finding is a `warning` always, and it blocks export because
its definition says so, not because its severity changes by context.

**Argument values** are either a literal string or an item reference:

```python
ArgValue = str | ItemRef      # ItemRef(uuid)
```

An `ItemRef` renders at display time through §5.3's rule — `name (3f2a91c4)`, or
`<deleted 3f2a91c4>` if the target is gone. Baking the name into the diagnostic
would leave stale names in a cached finding, and would lose the qualification
that shadowing makes necessary.

Worked example:

```python
Diagnostic(
    code="EXP201",
    subject=Subject(validator_uuid, Kind.VALIDATOR, (("expression", None),)),
    span=TextSpan(8, 21),
    args={"left": "real", "right": "decimal"},
)
```

renders as: *"`real` and `decimal` cannot be combined — binary floating point
would destroy the exactness of the decimal. Convert explicitly with `float(…)` if
that is what you intend."*

---

## 6. Related subjects

Many findings are about a *pair*: shadowing names two items, a duplicate name
names the other one, an unclosed Schema names the member and the target it
reaches outside.

```python
@dataclass(frozen=True, slots=True)
class Related:
    role:    str        # "shadows", "conflicts_with", "target", "anchor"
    subject: Subject
```

The model check list uses this to offer *go to the other one*, which for a
shadowing or duplicate-name finding is most of what the user wants. Without it
the finding names a problem the user then has to go hunting for.

---

## 7. Fix hints

```python
@dataclass(frozen=True, slots=True)
class FixHint:
    action: str                     # "add_schema_closure", "add_path_entity"
    label:  str                     # "Add the 3 missing entities"
    args:   Mapping[str, ArgValue]
```

A hint is a *name* the UI maps to a command, not a callable — the domain package
stays free of UI, and the mapping lives where the command stack does.

Populate it for the few findings with a genuine one-step remedy: unclosed Schema
(§9.2), a path entity that is not a member (§9.3), a widening override where a
narrowing Type exists. Leave it `None` everywhere else. It is cheap now and
awkward to retrofit, because retrofitting means revisiting every rule.

Whatever a hint triggers must be **one command** (§13.8) — a fix the user has to
undo four times is worse than no button.

---

## 8. Code ranges

Two families. `EXP` codes come from the expression checker and are already
defined in the signature table appendix §9. `MOD` and `LIB` codes come from the
model check.

| Range | Covers |
|---|---|
| `EXP1xx` | parse and whitelist |
| `EXP2xx` | operator typing |
| `EXP3xx` | function typing |
| `EXP4xx` | binding and arguments |
| `EXP5xx` | result and shape |
| `MOD1xx` | references — dangling, deleted composite operand, unset |
| `MOD2xx` | cycles — Type parent, Entity extension, Validator |
| `MOD3xx` | naming — duplicate, shadowing, blank |
| `MOD4xx` | entities and slots — narrowing, extension, identity, `on_delete` |
| `MOD5xx` | schemas — membership, closure, anchors, paths |
| `MOD6xx` | enforcement and export notes |
| `LIB1xx` | standard library — unknown built-in, deprecated built-in, version |

**Codes are permanent.** A retired code is marked retired and its number is never
reused, because a code that means one thing in v1 and another in v3 makes every
saved report and every test assertion a trap.

---

## 9. Identity, and incremental re-checking

A finding's identity is `(code, subject)` — deterministic, no counter, no
timestamp. Two findings with the same code at the same location *are* the same
finding.

That is what makes incremental update work. §13.8 re-checks after every command;
if the list were rebuilt wholesale the user's selection and scroll position would
jump on every keystroke-sized edit. With a stable key, the runner replaces the
findings for the affected subjects and leaves the rest — and the list widget
diffs cleanly.

**Which subjects are affected** comes from the command, which reports the item
UUIDs it touched, plus their dependents via the repository's `references_to`
(§12). But not every rule is item-local, which is why `CodeDefinition` carries a
`scope`:

| Scope | Re-run when | Examples |
|---|---|---|
| `item` | that item or a dependent changed | every `EXP` code, narrowing violations, unset references |
| `context` | any item in that Context changed | duplicate names, shadowing |
| `model` | on demand and before export | orphaned items, Entities in no Schema |

Without this distinction the incremental runner would either miss duplicate-name
findings — the second item's rename does not touch the first — or re-scan the
whole model on every edit. `model`-scope rules are the ones cheap to defer,
because none of them is urgent while typing.

---

## 10. Serialization

The record is `(code, subject, span, args, related, fix)`, all of it plain data
with UUIDs and strings. It serialises to JSON with no special handling.

That is not a v1 feature, but it is worth not breaking: `designer-model` is a
standalone package with no GUI (§14.1), so `python -m designer_model check
model.json --json` is a small script away, and a CI job that fails a build on any
`error` becomes possible without touching the domain code. Keeping names and
severities *out* of the record is what makes that report stable across versions.

---

## 11. Consequences — the impact dialog's own record

```python
@dataclass(frozen=True, slots=True)
class Consequence:
    kind:    ConsequenceKind    # the left column of §11.1's table
    subject: Subject            # the same locator
    args:    Mapping[str, ArgValue] = {}
```

`ConsequenceKind` enumerates §11.1 exactly: `membership_removed`,
`reference_cleared`, `parent_cleared`, `property_cleared`, `extension_cleared`,
`binding_removed`, `operand_orphaned`, `anchor_cleared`.

The dialog groups by `kind`, which is what §11.1 asks for — "3 Schemas lose a
member, 2 slots lose their target" rather than a flat list of seventeen items.
`extension_cleared` is rendered with the prominence §11.1 demands, since it
changes an Entity's shape rather than leaving a hole.

The delete planner returns `tuple[Consequence, ...]`, the dialog renders it, and
on confirmation the same tuple drives the fixups — so what the user was shown and
what happens are computed once, not twice. That is worth more than the shared
shape would have been.

---

## 12. Decisions taken

All twelve accepted, 29 August 2026. Nothing in this document is open.

One carries into the main specification as a change rather than a clarification:
**bindings gain a `uuid`** (§3), added to spec §5.6 and stored per spec §12.

