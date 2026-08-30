# Designer — Interfaces

30 August 2026. **Accepted**, with the five open questions decided (§10).
An appendix to the main specification: a seventh column and a fourth kind of
item.

Reconciled with *designer-signature-table.md* for base types and with
*designer-validator-library.md* for how a global library attaches to a model.

---

## 1. What an Interface is

**A Validator says yes or no about a value. An Interface presents a valid value
to a person, and reads a person's input back into a value.** They never overlap:

```
    parse:    "1.234,50"  ──▶  Decimal("1234.50")  ──▶  validators  ──▶  accept / reject
    present:  Decimal("1234.50")  ──▶  "1.234,50"
```

Parsing produces a *candidate* value. It does not decide whether the value is
allowed — that is the validators' job, and it happens after. Presenting happens
only to a value that is already valid.

This has one consequence worth stating plainly, because it is the thing that
will be tempting to break: **an Interface may never reject a value for being out
of range, too long, or the wrong shape.** `PIC 9(5)` does not mean "at most five
digits". It means "show five digit positions". A value needing six digits is a
*presentation* failure — the picture cannot render it — and that is reported as
a finding against the model, not as a validation failure at run time. If you
want six digits to be disallowed, that is `max_value` or `max_length`, and it
belongs to a rule.

Two mechanisms saying the same thing eventually disagree. This one says it once.

### What an Interface is not

- Not a constraint. See above.
- Not a type. It carries no meaning about what the value *is*, only about how it
  is written down.
- Not a layout. Field order, labels, grouping and widget choice belong to
  whatever builds the screen. An Interface describes one value.
- Not localisation. A picture is explicit — `dd-MM-yyyy` means what it says.
  Choosing which Interface a given audience sees is the application's business.

---

## 2. Where an Interface lives

**An item, like a Validator.** It has a UUID, a name, a description, a Context,
and it is visible from its Context downwards.

**No hierarchy.** An Interface has no parent and no chain. It is a leaf. This is
the property that makes it simple enough to be worth having, and it follows from
knowing only about base types: there is nothing to inherit *from*.

**A seventh column**, between Type and Property:

    Context · Validator · Interface · Type · Property · Entity · Schema

That keeps the strict dependency order the columns already have: an Interface
depends on nothing but the base types, exactly like a Validator, and a Type is
built from both.

---

## 3. What an Interface holds

| Field | Meaning |
|---|---|
| `base_type` | one of the eight. Required. |
| `picture` | the format, in the vocabulary for that base type |
| `decimal_point` | how the decimal separator is written. Numbers only (§5.1) |
| `group_mark` | how the grouping separator is written. Numbers only |
| `parse_lenient` | whether input may be sloppier than output is (§6) |
| `blank` | what an absent value presents as; how blank input parses back |

`base_type` is stored, not inferred. An Interface exists before any Type uses
it, so there is nothing to infer it from — this is the opposite of a Validator,
whose accepted types *are* inferred because its expression already implies them.

---

## 4. Binding an Interface to a Type

A Type may bind any number of Interfaces, and at most one is marked **default**.

    Money  ▶  money_uk       "#,##0.00"             1234.5  ▶  1,234.50    (default)
              money_compact  "#,##0.##"             1234.5  ▶  1,234.5
              money_ledger   "#,##0.00;(#,##0.00)"  -12     ▶  (12.00)

**A binding has no name of its own** `[DECIDED]`. An earlier draft of this
section gave each binding a name — `default`, `compact`, `ledger` — beside the
Interface's own name, which is two names for one thing and an invitation for
them to disagree. The Interface's name identifies it; the binding says only
*which* Interface and whether it is the default.

A name for the *role* a presentation plays for a particular Type — "grid",
"report", "entry" — is a reasonable thing to want later, and it is a field on
the binding when it is wanted. It is not needed to make this work, and a field
nobody has asked for is a field that will be filled in wrongly.

**A binding is legal only if the Interface's `base_type` equals the Type's base
type.** That is the whole of the compatibility rule, and it is why an Interface
needs no hierarchy: `Money`, `PositiveMoney` and any other decimal Type are
interchangeable as far as a decimal picture is concerned.

### Inheritance along the Type chain `[ACCEPTED]`

A Type that narrows another and binds no Interface of its own **uses its
parent's**, and where several ancestors bind one, **the deepest wins**. That is
the same rule as a narrowing slot: the more specific statement is the one that
applies.

The Interface has no hierarchy; the *Type* does, and presentation follows the
type chain the way validators and slots already do. The alternative — every Type
declaring its own presentation — means changing a format in one place and
finding four Types still showing the old one.

**The form says where it came from.** An inherited presentation that looks
declared is worse than no inheritance: somebody edits `PositiveMoney`, sees
`#,##0.00`, changes it, and has silently created a binding where there was
none. So a Type showing an inherited Interface names the ancestor it came from,
read-only, with an action to override it here — exactly as an inherited slot
does.

---

## 5. The picture vocabulary

One vocabulary per base type. A picture is checked against its base type when
it is written, so a nonsense picture is a finding, not a run-time surprise.

### 5.1 integer, decimal, real

| Symbol | Means |
|---|---|
| `0` | a digit position, always shown; a leading zero if the value is shorter |
| `#` | a digit position, shown only if the value needs it |
| `,` | grouping separator, at the position given |
| `.` | decimal separator |
| `-` `+` | sign position; `+` shows the sign always, `-` only when negative |
| `%` | present as a percentage, multiplying by 100 |
| `;` | separates the positive picture from the negative one |

    #,##0.00      1234.5   ▶  1,234.50
    0000          42       ▶  0042
    #,##0.00;(#,##0.00)     -12  ▶  (12.00)
    0.0%          0.075    ▶  7.5%

**One spelling.** `[DECIDED]` COBOL `PIC` was considered as a second spelling —
`9(5)V99` for `00000.00` — and left out. Two spellings mean two grammars to
check, two sets of findings to word, and two things to explain. If it is wanted
later it is a translator into this vocabulary, not a second vocabulary.

`%` is valid for **decimal and real only**. `[DECIDED]` On an integer the
smallest step a percentage can express is 100% — stored 1 shows as 100%, and
7.5% is unreachable — so a percentage picture on an integer is always a
mistake. The stored value is a fraction: 0.075 presents as 7.5%.

### 5.1.1 Regional separators `[DECIDED]`

**The picture is always canonical — `.` decimal, `,` grouping — and two fields
say how those are written.** `#,##0.00` with `decimal_point = ","` and
`group_mark = "."` presents `1.234.567,50`.

| | picture | decimal | grouping | presents |
|---|---|---|---|---|
| UK, US | `#,##0.00` | `.` | `,` | `1,234,567.50` |
| Germany | `#,##0.00` | `,` | `.` | `1.234.567,50` |
| France | `#,##0.00` | `,` | space | `1 234 567,50` |
| Switzerland | `#,##0.00` | `.` | `'` | `1'234'567.50` |

One picture, four regions. That is the point: the *structure* — grouped by
three, two decimals — is the same everywhere, and only two characters differ.

Writing the separators literally in the picture was considered and rejected.
With both present, `#.##0,00` is unambiguous; with only one, `#,##0` and `0,00`
are indistinguishable, and the rule needed to tell them apart — "the last
separator is the decimal one" — reads `#,##0` as *zero with two decimals*.
A grammar that is ambiguous in its commonest case is not a grammar to build on.

Allowed: `.` `,` `'` space and non-breaking space; empty for grouping, to write
a group size that shows no separator. The two must differ.

**Dates need no equivalent.** A region writing `30/08/2026` writes
`dd/MM/yyyy`: the separator there is literal text, not a role, so a different
picture is the honest answer rather than a setting.

**Locales are not modelled.** No `de-DE`, no CLDR. That would decide currency
symbols, digit shapes and calendars along with the separators, and §1 already
says which Interface a given audience sees is the application's business. Two
explicit characters are the whole of the regional difference this vocabulary
has.

### 5.2 string

| Symbol | Means |
|---|---|
| `X(n)` | n character positions |
| `<` `>` `^` | align left, right, centre within the positions |
| `U` `L` | present upper-cased, lower-cased |

    X(30)<        "Ada"  ▶  "Ada                           "
    X(3)U         "gbp"  ▶  "GBP"

Presenting is padding and case only, and **never truncates**. `[DECIDED]`

`X(n)` is a *hint about width*, not a limit: it says how much room to give the
value, and an application may scroll, wrap or widen when a value needs more.
A value longer than its positions presents as itself, unpadded — so the
round-trip law still holds, because parsing strips padding that is not there.

If a length is meant to be a limit, that is `max_length`, and it is a rule.

### 5.3 date, time, datetime

`yyyy MM dd HH mm ss` with the usual meanings, `SSS` for milliseconds, `ZZ` for
the offset. Literal text in quotes.

    dd-MM-yyyy              2026-08-30  ▶  30-08-2026
    yyyy-MM-dd'T'HH:mm:ssZZ             ▶  2026-08-30T14:22:05+00:00
    HH:mm                               ▶  14:22

A datetime is stored in UTC (spec §4.1). A picture with no `ZZ` presents the UTC
value and parses input as UTC; a picture with `ZZ` presents the offset and
accepts one. **No picture may introduce a local timezone**, because the model
does not carry one and inventing it here would put a rule about time in the
presentation layer.

### 5.4 boolean

Two labels, separated by `;`, positive first.

    Yes;No        true  ▶  Yes
    ✓;✗
    1;0

---

## 6. Parsing

**Parsing is the inverse of presenting, and the two must agree.** The law:

    parse(present(v)) == v      for every value the Type admits

That is checkable, and §7 makes it a check. It is also where most picture bugs
live: `#,##0.00` on a Type allowing four decimal places rounds on the way out
and cannot recover the original on the way back.

### Reversibility depends on the Type's rules `[FOUND WHILE BUILDING]`

The law is quantified over *the values the Type admits*, and that turns out to
matter more than it looks. Three pictures that are perfectly good on one Type
and lossy on another:

| Picture | Reversible when the Type has | Lossy without it |
|---|---|---|
| `X(3)U` | `is_uppercase` | `gbp` presents as `GBP` and reads back as `GBP` |
| `X(6)<` | `trimmed` | `" ada "` loses its own spaces among the padding |
| `#,##0.00` | `max_scale(2)` | `1234.5678` presents as `1,234.57` |

None of these is a fault in the picture, and none is a fault in the rules. It is
the *pair* that is wrong, which is why `INT202` is checked against the Type the
Interface is bound to rather than against the picture alone.

This is the payment for keeping the two mechanisms separate, and it is worth
paying: the alternative is a picture that quietly constrains, which is the thing
§1 exists to prevent.

`parse_lenient` (default **on**) additionally accepts input that differs from
the presented form in ways that cannot change the value:

- leading and trailing whitespace
- a missing grouping separator — `1234.50` where `1,234.50` was presented
- either case for boolean labels and for `U`/`L` strings
- a missing sign where the picture always shows one

Anything else fails to parse, and a parse failure is *not* a validation failure:
the application has nothing to hand to the validators, so it reports the input
as unreadable rather than as invalid. The distinction matters — "that is not a
date" and "that date is in the future" are different sentences to show somebody.

---

## 7. What the checker verifies

New codes, `INT1xx`, in the existing severity scheme. Six of the nine are in the
registry; `INT202`, `INT401` and `INT402` are steps 5 and 6 of §9 and are marked
below, because a code table that does not say which codes exist is a table
somebody will trust.

| Code | Severity | Blocks export | Says |
|---|---|---|---|
| `INT101` | incomplete | yes | Interface has no base type yet |
| `INT102` | incomplete | yes | Interface has no picture yet |
| `INT201` | error | yes | the picture is not valid for `{base_type}` |
| `INT202` | error | yes | the picture is ambiguous: `{detail}` cannot be parsed back — **specified, not yet implemented** |
| `INT301` | error | yes | bound to `{type}`, whose base type is `{other}` |
| `INT302` | error | yes | two Interfaces on `{type}` are both marked default |
| `INT401` | warning | no | presenting loses precision: `{picture}` shows {n} decimals of a value allowing {m} — **specified, not yet implemented** |
| `INT402` | note | no | `{picture}` gives {n} positions to a value `{validator}` allows {m} — **specified, not yet implemented** |
| `INT601` | note | no | Interface is bound to nothing |

`INT402` is a **note**, not a warning. `[DECIDED]` If a Type says
`max_length(40)` and its Interface says `X(30)`, nothing is wrong with either
and nothing will fail: the width is a hint, and the application scrolls. It is
worth saying once, because the designer may not have intended a field narrower
than its data, but it is information rather than a fault.

---

## 7.1 The document version `[DECIDED]`

Interfaces make the document shape wider: a new `interfaces` group, and an
`interfaces` list on each Type. That is `schema_version` 2.

**A document declares the lowest version that can represent it.** A model with
no Interfaces stays at 1 and keeps loading in an older build; one that uses them
is written as 2, and an older build refuses it with the message it already has
for a newer file. Bumping every document on save would strand models that never
used the feature, for nothing.

Loading is unchanged: a version-1 file has no `interfaces` key, which reads as
none, and the round trip stays byte-identical.

---

## 7.2 Deleting an Interface `[DECIDED]`

No refusal, and no cleverness. The deletion is deliberate; the useful thing is
to say what each affected Type will present with *afterwards*.

    PositiveMoney — will present with money_uk, from Money
    Money         — no presentation will remain

The fallback is just §4 applied once the binding is gone: the Type's own next
binding if it has another, otherwise the nearest ancestor's, otherwise nothing.
"No presentation will remain" is worth saying and is not a fault — a Type
without one is an ordinary state, and the note is there so the outcome is never
a surprise.

The consequence names the **outcome, not the mechanism**. "A binding was
removed" is true and useless; what the column will look like tomorrow is what
somebody needs in order to decide.

---

## 8. What the export carries

Each column of an exported Schema gains an optional `interface` block:

```json
{
  "name": "total",
  "base_type": "decimal",
  "constraints": [">= 0", "scale <= 2"],
  "interface": {
    "name": "default",
    "picture": "#,##0.00",
    "decimal_point": ".",
    "group_mark": ",",
    "parse_lenient": true,
    "blank": ""
  }
}
```

**The separators travel with the picture** `[DECIDED]`, and are always written
out even when they are the canonical `.` and `,`. The picture alone does not say
how to render a number — that is the whole point of §5.1.1 — so a generator
reading `#,##0.00` and assuming a full stop would produce English output from a
German model. A generator that has to know a default is a generator that can get
it wrong.

They appear for numeric columns only. For a date, a string or a boolean the
picture is complete on its own:

```json
{
  "name": "ordered_on",
  "base_type": "date",
  "interface": { "name": "european", "picture": "dd-MM-yyyy", "blank": "—" }
}
```

Resolved like everything else in the export: the name it was bound under and the
picture, with no reference to the Interface item. A database generator ignores
the block; a form generator uses it; neither needs to know the Interface
existed.

**An inherited Interface exports as though it were declared.** If `PositiveMoney`
takes its presentation from `Money` (§4), the column carries the picture and the
name it was bound under, and says nothing about the inheritance. Resolved means
resolved: the export is for generators, and where a format came from is a fact
about authoring. The form is where the provenance is shown, to the person who
can act on it.

---

## 9. What I would build first

1. ~~The picture engine: all four vocabularies, present, parse, round trip, and
   the regional separators.~~ **Built** — `designer_model/pictures.py`, 53
   tests. It went first because it is the part with real design in it, and
   because it is testable without any of the plumbing below.
2. ~~The `Interface` item: dataclass, persistence, identity,
   `INT101`/`INT102`/`INT201`/`INT301`/`INT302`/`INT601`, the deepest-wins
   resolution of §4, and deletion.~~ **Built** — 29 tests.
3. ~~The seventh column, and the form.~~ **Built** — with a live preview: a
   picture shows what it does to a few sample values, and says when they do
   not read back.
4. ~~Binding to a Type, with the deepest-wins inheritance of §4 and the
   provenance line.~~ **Built.**
5. `INT202` against the bound Type — the round trip over the values that Type
   admits, which is where §6 says the interesting failures are.
6. `INT401`/`INT402`, comparing pictures against the Type's rules.

Steps 2 and 3 are enough to find out whether the vocabulary is right before
much is written in it.

---

## 10. The five questions, decided

1. **Inheritance along the Type chain** — yes, deepest wins, and the form names
   where it came from (§4).
2. **COBOL `PIC`** — not now. A translator later if wanted, never a second
   vocabulary (§5.1).
3. **`blank`** — the Interface's. A designer who wants the application to decide
   sets it to `""` and does the mapping there.
4. **Truncation** — none. `X(n)` is a width hint, not a limit (§5.2).
5. **Percent** — decimal and real only, stored as a fraction (§5.1).
