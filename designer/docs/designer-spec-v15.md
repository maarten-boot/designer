# Designer — Specification (revision 15)

Original: 27 August 2026. Revised: 29 August 2026.

Markers:

- `[DECIDED]` — settled in review; recorded with its consequence.
- `[OPEN]` — still to decide. None block starting work.
- `[V2]` — deliberately deferred.

Three companion documents are part of this specification, all accepted:

- *designer-validator-library.md* — the built-in Validators. §5.7 records how
  they attach to the model.
- *designer-signature-table.md* — the complete operator and function signature
  table, the type universe, and the `EXP` diagnostic codes. It is authoritative
  for everything §5.4 and §5.6 summarise.
- *designer-diagnostics.md* — the diagnostic and consequence records, the code
  registry, and the incremental re-check scopes. Authoritative for §11.6 and for
  the impact dialog's record in §11.1.

---

## 1. Purpose

Designer is a desktop tool for authoring and browsing a **data model**: a
catalogue of reusable validation rules, type definitions, fields, record
structures and the schemas that group them, organised into namespaces.

The tool edits the model itself. It does not execute the model against real data
(see §15, test bench).

The model targets a relational backing store. Entity extension, entity
references, flattened materialization and the deferral of collections in §8 all
follow from that.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| Item | Any addressable model object: BaseType, Validator, Type, Property, Entity, Schema, Context. |
| Kind | The class of an item (`Validator`, `Type`, …). |
| Reference | A pointer from one item to another, stored by UUID. |
| Slot | The use of a Property, or of another Entity, inside one Entity. |
| Binding | The attachment of a Validator to a Type, Entity or Schema, with its arguments supplied (§5.6). |
| Built-in | A Validator from the standard library: global, read-only, not stored in the model file (§5.7). |
| Path | A route from an anchor Entity through reference slots to a value slot (§9.3). |
| Command | One committed user action, the unit of undo — however many objects it touches (§13.8). |
| Abstract Entity | A modelling-only Entity that never becomes a table. |
| Concrete Entity | An Entity that materializes as one flattened table. |
| Context | A modelling namespace controlling visibility. Hierarchical, exclusive. |
| Schema | An explicit, curated set of concrete Entities plus the rules spanning them. |
| Closed Schema | A Schema whose members reference only other members (§9.2). |

---

## 3. Common item structure

Every item, **including Context and Schema**, has:

| Field | Type | Notes |
|---|---|---|
| `uuid` | UUID | Immutable. All references use this, never the name. |
| `name` | string | Must match `[A-Za-z_][A-Za-z0-9_]*` once non-empty. Unique per (Context, kind). May be empty while authoring (§3.1). |
| `description` | string | Free text, may be empty. |
| `created` | timestamp | Set once, UTC. |
| `modified` | timestamp | Updated on change to the item's own fields only. Does not propagate to referencing items. |

Renaming never breaks references, because references are by UUID — including
inside composite expressions (§5.2).

### 3.1 Items may be incomplete `[DECIDED]`

**A new item is created empty**: blank name, blank description, every reference
null, every list empty.

- **The in-memory model tolerates nulls** where §6 and §8 describe required
  references. A Type with no parent is a legal object; it is not a legal *export*.
- **The file format tolerates them too** (§12).
- **The model check has a third severity**, `incomplete`, alongside `error` and
  `warning` (§11.6). Incomplete never blocks saving; it will block export.
- **Save is always allowed.**
- Invariants split in two: a *cycle* in a parent chain is an error, because it is
  wrong rather than unfinished; a *missing* parent is incomplete.
- Blank names show as `<unnamed Type>` and are skipped by the uniqueness check.

This principle is also why **no edit is ever blocked for being invalid** (§13.8)
and why **no delete is refused** (§11): the model holds broken states and
describes them rather than preventing them.

New items are created in the **active Context**, shown in the breadcrumb (§13.4).

---

## 4. BaseType `[DECIDED]`

Eight fixed, built-in scalar types, not editable by the user:

| BaseType | Notes |
|---|---|
| `integer` | |
| `real` | Binary floating point. May hold NaN and infinity, which no backing store accepts — see `is_finite` in the library. |
| `decimal` | Exact. Never mixes with `real` (§5.6). |
| `boolean` | |
| `string` | |
| `datetime` | Timezone-aware, always UTC (§4.2). |
| `date` | No time component, no zone. |
| `time` | No date component, no zone. Comparison only (§4.3). |

`null` is **not** a BaseType. Optionality belongs to the slot, as `required`
(§7.2).

BaseTypes are global, have no Context, and are the roots of the Type hierarchy.
The standard library (§5.7) is global on the same terms.

**Precision and scale** for `decimal` are expressed with the built-in
`max_precision` and `max_scale` validators, which the exporter recognises **by
UUID** to emit `NUMERIC(p, s)`. Recognition is by identity, not by parsing, so a
forked copy (§5.7) is not recognised.

### 4.1 Literals

| BaseType | Storage form |
|---|---|
| `decimal` | Decimal string. A JSON number would silently round. |
| `datetime` | ISO-8601 with a `Z` suffix: `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` |
| `date` | ISO-8601, `YYYY-MM-DD` |
| `time` | ISO-8601, `HH:MM:SS[.ffffff]` |

A **list literal** (§5.6) is a JSON array of these forms, homogeneous in BaseType.

### 4.2 Timezone policy `[DECIDED]`

`datetime` is **timezone-aware and always UTC**, serialised with a `Z` suffix. A
naive literal is rejected on entry and on load; a non-UTC offset is normalised to
UTC and the original is not retained. Export maps `datetime` to `timestamptz`.
Two `datetime` values are therefore always comparable.

`date` and `time` remain zone-free, because a calendar date and a wall-clock time
are not instants — which is why `date` and `datetime` may not be compared without
an explicit conversion.

### 4.3 `time` arithmetic `[DECIDED]`

`time` supports **comparison only**. Wrapping at midnight would quietly turn
23:00 + 2h into 01:00; anyone wanting that should model a duration.

`duration` still arises, from `datetime − datetime` and `date − date` (§5.6).

---

## 5. Validator

A named, reusable predicate.

### 5.1 Leaf and composite

A Validator is **either** a leaf or a composite, never both.

**Leaf**

| Field | Notes |
|---|---|
| `parameters` | Ordered list of parameter names. May be empty. |
| `expression` | Predicate **source text**, returning boolean. |
| `message` | Shown when the predicate returns false. May interpolate parameters. |

An empty `parameters` list means the expression uses a single implicit argument
named `value`.

**Composite**

| Field | Notes |
|---|---|
| `parameters` | Union of what the operands need. |
| `expression` | **Source text** of a boolean expression over other Validators, using `AND`, `OR`, `XOR`, `NOT` and parentheses. Operands are stored as UUIDs (§5.2). |
| `message` | Optional; see §5.5. |

**Validators are not typed.** A Validator declares parameter *names*, not
parameter BaseTypes, so `between(min, max)` serves `integer`, `decimal`, `date`
and `datetime` alike. Types are known only at the **binding** (§5.6).

### 5.2 Expressions are stored as source; composite operands are UUIDs `[DECIDED]`

Both kinds are stored as **source text**, with the parse tree derived on demand
and cached. An edit commits when the user leaves the field (§13.8), so a
half-written expression must be able to commit; if the stored form were a tree,
unparseable text would have nowhere to live.

**Inside a composite, operands are stored as UUIDs**, not names:

```
stored     3f2a91c4-… AND (7b10de55-… OR a4c8fe02-…)
displayed  non_empty AND (is_email OR is_url)
```

- **Substitution is token-level, not parse-level**, done with a small tokenizer,
  so it works on expressions that do not yet parse.
- **On commit**, each identifier resolves through the Validator's Context scope
  (§10) — and through the standard library, which is in scope everywhere (§5.7) —
  and is replaced with the target's UUID. An identifier that resolves to nothing
  is **left as written**, and the checker reports an unresolved operand. Storage
  never fails.
- **On display**, each UUID is replaced with the target's current name. A UUID
  with no target renders as `<deleted 3f2a91c4>` and is an error.
- The user's whitespace and parenthesisation survive the round trip.

The editor shows **bare names**; messages and diagnostics use the qualified form
(§5.3).

### 5.3 Naming in messages and diagnostics `[DECIDED]`

Wherever a Validator is named to the user outside the expression editor — failure
messages, model-check findings, the impact dialog — it appears as **`name (uuid)`**,
with the UUID abbreviated to its first eight characters and the full value
available by copy or hover. A deleted target shows `<deleted 3f2a91c4>`; an
unnamed one shows `<unnamed> (3f2a91c4)`.

### 5.4 Expression evaluation `[DECIDED]`

**Composite expressions get a dedicated parser, now.** Identifiers, `AND` / `OR`
/ `XOR` / `NOT`, parentheses — recursive descent, roughly 80 lines. Python `eval`
is wrong here: `and` and `or` short-circuit and return operands rather than
booleans, and Python has no `xor` keyword.

**Leaf expressions are evaluated with `eval` for v1**, parsed and type-checked
first (§5.6). All expression handling goes through one `expressions` module
exposing `parse`, `check`, `evaluate`, and the substitution helpers from §5.2.
Nothing else calls `eval` or `compile`, so the linter suppression lives in
exactly one file (§14.2).

**Attribute access is banned outright** — no case analysis, no exceptions. This
is why the string operations below are free functions rather than methods.

The evaluation namespace, and the call whitelist, is exactly:

| Function | Signature |
|---|---|
| `len(s)` | string → integer |
| `lower(s)`, `upper(s)`, `strip(s)` | string → string |
| `starts_with(s, p)`, `ends_with(s, p)`, `contains(s, p)` | string, string → boolean |
| `regex_full_match(s, pattern)` | string, string → boolean |
| `is_finite(x)` | real → boolean |
| `precision(x)`, `scale(x)` | decimal → integer |
| `now()` | → datetime, **non-deterministic** |
| `today()` | → date, **non-deterministic** |
| `current()` | → datetime or date, by context — **non-deterministic** (§5.7) |
| `seconds(n)`, `minutes(n)`, `hours(n)`, `days(n)`, `weeks(n)` | numeric → duration |
| `total_seconds(d)`, `total_days(d)` | duration → real |
| `abs`, `min`, `max`, `round`, `int`, `float`, `str` | as in Python |
| `decimal(s)` | string or integer → decimal; **`decimal(real)` is rejected** |

The duration constructors are what make `duration` usable at all: it arises from
`datetime − datetime` but had no literal form, so `(end - start) < days(30)` was
previously unwriteable. They also name their units at the call site, which is why
bare `date + 30` is rejected with a message pointing at `days(30)`.

`decimal` is lowercase, matching every other type name — the capitalised
`Decimal` leaked a Python detail into a user-facing language. The `datetime`
callable is dropped; temporal literals cover every case.

`regex_full_match` anchors both ends. A partial match is the commonest source of
a validator that silently passes everything; anyone wanting a search writes
`.*…​.*`. **Its pattern argument must be a literal**, or a parameter bound to
one, so the pattern compiles at authoring time — a malformed regex becomes an
error with the compile message rather than a runtime failure — and caches by
pattern string. `[V2]` A user-supplied
pattern can backtrack catastrophically and Python's `re` has no timeout; the
blast radius here is a hung UI during the test bench, so the guard belongs with
the test bench, which should evaluate off the UI thread.

There is **no name collision** between whitelisted functions and Validators. A
bare identifier in a *leaf* expression is a parameter or a function; in a
*composite* it is a Validator. The two namespaces never meet — though the library
still avoids reusing a function's name for a validator, since a human reader has
no such guarantee.

The whitelist visitor that makes `eval` safe is the same `ast.parse` walk the
checker already performs, with a rejection list attached. Both are v1.

### 5.5 Constraints and failure messages

- A Validator must not reference itself, directly or transitively.
- A composite's operands must be resolvable in its scope (§10) or in the library.

If a composite has its own `message`, report only that. Otherwise report the
operands that contributed to the failure — for `AND`, the failing operands; for
`OR`, all of them; for `NOT`, a negated form — each named per §5.3.

A **binding may override the message** (§5.6), which takes precedence over the
Validator's own.

### 5.6 Bindings and static type checking `[DECIDED]`

A **binding** attaches a Validator to a Type, an Entity or a Schema:

| Field | Notes |
|---|---|
| `uuid` | Immutable identity for the binding itself. Diagnostics locate a finding by it, the impact dialog names a removed binding by it, and the inline feedback matches findings to the row it is drawing (appendix *diagnostics* §3). |
| `validator` | Reference to a Validator, authored or built-in. |
| `arguments` | One per declared parameter (below). |
| `message` | **Optional override** of the Validator's message. |

The message override exists because a message living only on the Validator makes
every use of `max_length` say the same thing — fine for a postcode, poor for a
product code with a documented format. It is half a field on a structure that
already exists, and it removes the main reason to fork a built-in, which would
also cost exporter recognition (§4).

**Argument values** are one of:

- the implicit `value`, or a value slot, or a path (by site, below);
- a **scalar literal** of a BaseType;
- a **list literal** — a homogeneous list of scalar literals, for `in` and
  `not in`. This is what makes an enumeration expressible: a Type over `string`
  with `one_of(["draft", "sent", "paid"])`. Earlier revisions assumed enums were
  already possible; without list arguments they were not.

Three binding sites:

- **Type → Validator.** The value's BaseType comes from the Type's parent chain.
- **Entity → Validator.** Each parameter binds to a **value slot** (§7.2).
- **Schema → Validator.** Each parameter binds to a **path** from an anchor
  Entity (§9.3).

The check applies to all three because a Validator is reusable: an expression
sound for the Type it was written against can be nonsense for the next Type that
attaches it. The mismatch is a property of the binding, never of the Validator
alone. A binding whose type cannot yet be determined is `incomplete`.

**The checker** infers a type for every node and reports:

- mixed `decimal` and `real` in arithmetic — error;
- comparison between incompatible BaseTypes — error;
- `date` compared with `datetime` — error (§4.2);
- any arithmetic on `time` — error (§4.3);
- a list literal that is not homogeneous, or whose element type does not match
  the value — error;
- a top-level result that is not `boolean` — error;
- a parse failure — error, carrying the offset so the editor can mark it;
- an unresolved or deleted composite operand — error (§5.2);
- any parameter never used — warning.

**The internal type lattice is larger than the BaseType set.** Subtracting two
`datetime` or two `date` values yields a duration — a legitimate intermediate
value, never the type of a slot, a Property, or a top-level result.

**Signatures live in the appendix**, *designer-signature-table.md*, as a module
of pure data walked by the checker. Every binary operator's full type matrix is
rendered and committed as a golden file, so a pair nobody considered appears as
an explicit "no rule" cell rather than hiding, and any later change shows up as a
reviewable diff.

Five rules from that document shape the rest of this specification:

- **`unknown` absorbs.** Any operation with an `unknown` operand yields `unknown`
  and reports nothing. This is required by §3.1: a Type with no parent has no
  BaseType, and without absorption every binding on it would erupt in errors
  while the user is still filling the form. `unknown` never *satisfies* a
  requirement, only suppresses a complaint, so such a binding is still reported
  as `incomplete`. It doubles as the poison type after a failure, so one mistake
  produces one diagnostic rather than a cascade.
- **Numeric literals in expressions are untyped** and take the type of their
  context, so `price <= 1.5` on a `decimal` price is not a real/decimal error.
  Unconstrained, an integer-shaped literal defaults to `integer` and a
  fraction-shaped one to `decimal` — the source text is exact, and reading it as
  binary floating point would lose what the user wrote.
- **Parameter types are inferred by unification**, not annotated. From
  `min <= value <= max` with `value: date`, both parameters resolve to `date` and
  the binding form offers date pickers. This is what keeps "Validators are not
  typed" workable.
- **No implicit truthiness**, no `is`, no substring `in`, no floor division. Each
  is rejected with its own message rather than silently meaning something.
- **Chained comparisons are supported** — `min <= value <= max` is one node with
  two comparators, and half the standard library is written that way.

### 5.7 The standard library `[DECIDED]`

A library of built-in Validators ships with the tool. Its contents are specified
in *designer-validator-library.md*; what follows is how it attaches.

**Global and read-only**, on the same terms as BaseTypes: no Context, visible
everywhere, not editable, not deletable, and **never written to the model file**.
Only references to built-ins are stored.

- **Stable identifiers.** Each built-in's UUID is
  `uuid5(NAMESPACE_STDLIB, canonical_name)`, where `NAMESPACE_STDLIB` is itself
  `uuid5(NAMESPACE_DNS, "stdlib.designer")` — deterministic, identical on every
  installation, and structurally distinct from the v4 UUIDs of authored items.
- **Shipped as a JSON model fragment**, package data inside `designer-model`
  (§14.1), loaded at startup into a read-only registry. No second code path: a
  built-in is a Validator, and the registry is simply a second source for name
  resolution and UUID lookup. This also makes the library the first real exercise
  of the file format.
- **`library_version`**, an integer, is recorded in every model file beside
  `schema_version` (§12). It increments when a built-in is added, deprecated, or
  changes meaning; a message reword does not bump it.
- **Built-ins are never removed**, only deprecated: still resolvable, still
  functional, marked in the interface, excluded from pickers. A reference to a
  UUID this installation does not have produces a named diagnostic — "requires
  standard library v3, this is v2" — rather than a dangling reference.
- **Fork to model** copies a built-in into the active Context as an ordinary
  editable Validator with a fresh v4 UUID. Existing bindings keep pointing at the
  built-in; the fork is a starting point, not a replacement. This is what makes
  read-only acceptable.

**Determinism is derived, not declared.** A Validator is non-deterministic when
its expression calls `now()` or `today()`, or when any composite operand is. The
checker computes it; nothing is stored.

A binding to a non-deterministic Validator **cannot be enforced by the database**.
PostgreSQL rejects non-immutable functions inside a CHECK constraint, so this is
a real database rule rather than an invented one. Therefore:

- A **Schema** binding has its `enforcement` locked to `application` (§9.4), with
  the reason shown.
- A **Type or Entity** binding has no enforcement flag, so instead it is excluded
  from CHECK generation on export and reported as a warning (§11.6): the rule is
  real, but only application code can enforce it.

**Polymorphic temporal built-ins.** `in_past` and its siblings are written
against `current()`, a constrained polymorphic function returning `datetime` or
`date` (§5.4). `in_past` is simply `value < current()`: unification gives
`current()` the type of `value`, so it means `now()` on a `datetime` and
`today()` on a `date`. Binding to a `time` fails the constraint — "in the past"
is undefined for a wall-clock time with no date — and binding to `unknown` stays
silent. No dispatch machinery beyond the unification already present.

---

## 6. Type

A named restriction of a BaseType.

| Field | Notes |
|---|---|
| `parent` | Reference to a BaseType or another Type. Exactly one once complete; null while authoring. |
| `validators` | Ordered list of bindings (§5.6). |

The **effective validator set** is the parent's followed by this Type's own.
Validation is conjunctive.

The **base type** is derived from the parent chain, not stored. Cycles are
errors; an unset parent is incomplete.

**Type narrowing.** Type `B` narrows Type `A` when `A` appears in `B`'s parent
chain. Both share a BaseType, and `B`'s effective validator set is a superset of
`A`'s. A cheap chain walk, and §8.1 depends on it.

Structural recursion is not a Type concern; a self-referential model uses an
entity reference, §8.3.

---

## 7. Property and Slot

### 7.1 Property `[DECIDED]`

A **shared, reusable field definition** — one Property, referenced by many
Entities.

| Field | Notes |
|---|---|
| `type` | Reference to a Type or BaseType. |

Nothing that varies per use may live on the Property. Required, default and
position are per-Entity facts and live on the Slot.

### 7.2 Slot

The use of something inside one Entity. Not a top-level item, edited in the
Entity form.

| Field | Notes |
|---|---|
| `slot_name` | Defaults to the Property or Entity name; overridable, so one Entity can hold two references to the same target (`author`, `reviewer`). |
| `kind` | `value` or `reference`. |
| `required` | Boolean. Maps to `NOT NULL`. |
| `position` | Ordinal within the Entity. |

A **value slot** additionally has `property`, an optional `default`, and an
optional `type_override` (§8.1).

**Entity validators bind to value slots only.** A reference slot has no scalar
value to test. Reference slots appear in Schema validators only as *navigation*,
never as the final term of a path (§9.3).

---

## 8. Entity

| Field | Notes |
|---|---|
| `abstract` | Boolean. See §8.1. |
| `extends` | Optional reference to another Entity. Single inheritance. |
| `slots` | Ordered list of Slots. |
| `validators` | Optional bindings naming **value slots** of this Entity. Row-local rules. |
| `identity` | Optional list of slots forming the primary key. |
| `indexes` | List of (slot list, `unique` flag). |
| `default_order` | List of (slot, ascending) pairs. |

Entity validators are **row-local**: every parameter resolves within one row, so
the rule maps onto a CHECK constraint — unless it is non-deterministic (§5.7).
Rules that span tables live on a Schema.

### 8.1 Extension, abstraction and narrowing `[DECIDED]`

Single inheritance, acyclic.

**Effective slots** = the parent's, then this Entity's own.
**Effective validators** = the parent's, then this Entity's, conjunctive.

**Abstract Entities** never materialize. They may not be reference targets, may
declare `identity` and `indexes` for descendants to materialize, warn when they
have no concrete descendant, and are **never Schema members**.

**Materialization is flattened**: each concrete Entity becomes one table with all
its effective slots as real columns. Concrete-table inheritance; §8.2 covers the
cost.

**Slot narrowing.** A descendant may redeclare an inherited `slot_name`:

- The slot kind may not change.
- `type_override` must narrow the inherited Type (§6). Widening is rejected.
- `required` may go false → true, not true → false.
- `default` may be replaced, and must satisfy the narrowed Type.
- A **reference slot's target may not be narrowed**.

Because each concrete table is flat, a narrowed slot's constraints are the
constraints on that table's own column — which is why narrowing works here and
would not under joined-table inheritance.

**Identity** is inherited when an ancestor declares it.

### 8.2 Extension does not give polymorphic references

Flattened materialization means there is no shared base table for a foreign key.

- A reference to an **abstract** Entity is rejected.
- A reference to a **concrete** Entity with concrete descendants reaches only that
  Entity's own rows. The model check warns.

Use extension with an abstract base, and keep concrete Entities as leaves.

`[V2]` Per-chain joined-table inheritance, which would forbid narrowing on that
chain. Scalar unions stay out — no mainstream relational database has a sum type,
and `one_of` (§5.6) covers the enumeration case that motivates most requests.

### 8.3 Entity references `[DECIDED]`

| Field | Notes |
|---|---|
| `target` | Reference to a **concrete** Entity. |
| `inverse_name` | Optional name for the reverse accessor. |
| `on_delete` | `restrict` / `cascade` / `set_null`. `set_null` requires `required = false`. |

- The target must be concrete and have an identity.
- The target must be **visible** from this Entity's Context (§10).
- **To-one only.** See §8.4.
- Reference cycles are allowed, including self-reference.
- `required` maps to `NOT NULL` on the foreign key.

`on_delete` describes the *generated database*, not Designer's own delete
behaviour (§11) — two different things that share a word.

### 8.4 Collections `[V2]`

One-to-many is modelled from the child side; many-to-many is an explicit join
Entity holding two references.

---

## 9. Schema

An explicit, curated set of concrete Entities, plus the rules spanning them.

| Field | Notes |
|---|---|
| `members` | Explicit list of concrete Entity references. |
| `validators` | Cross-entity bindings (§9.3). |

### 9.1 Membership is explicit and non-exclusive `[DECIDED]`

**Nothing joins a Schema by itself.** A new Entity belongs to no Schema until
someone adds it. A Schema states what is *in* a deliverable, and must not drift
because someone added a table three Contexts away.

**An Entity may belong to any number of Schemas.** An `Address` or `Currency`
defined once in a high Context can be a member of every Schema that needs it.

- Members must be **concrete**.
- Members must be **visible from the Schema's Context** (§10) — which makes
  "defined higher up, reused lower down" the natural idiom.
- Any number of Schemas may live in one Context; there is no "schema root".
- A Schema with fewer than two members is legal, reported as informational.

Two Schemas sharing a member is normal and is **not** flagged.

### 9.2 Closure, checked on add `[DECIDED]`

A Schema is **closed** when, for every member, every reference-slot target is
also a member. Extension does not affect closure — inherited slots are flattened
into the member's own table.

**Closure is computed when a member is added**, before the add takes effect:

1. The transitive reference closure of the new member is computed. Reference
   cycles are normal; the walk carries a visited set.
2. Anything already a member drops out.
3. **If anything remains, a dialog shows exactly what would be pulled in**, with
   its count, before the user confirms.
4. On confirm, the member and its closure are added — **one command** (§13.8). On
   decline, only the named member is added and the Schema is left unclosed, with
   the standard warning.

**Where the closure cannot complete.** A needed Entity may not be visible from
the Schema's Context, and §9.1 forbids adding it. The dialog lists such entities
separately, as blocked and why; the add proceeds without them. The fix is a
modelling one — move the shared Entity higher — not something the dialog can do.

**Removal is checked too.** Removing a member that other members reference leaves
the Schema unclosed; the confirmation names which members would then dangle.

Closure is not required while modelling, is reported as a **warning**, and is
**required for export**. The Schema form also keeps **Add missing referenced
entities** as a standalone action (§13.6).

### 9.3 Cross-entity validators and anchored paths `[DECIDED]`

`entity.property` alone does not define a rule. `Order.total` and `Invoice.total`
name two columns in two tables, but a predicate over them has no meaning until
something says **which Order row pairs with which Invoice row**.

So a Schema binding carries an **anchor** and **paths**:

| Field | Notes |
|---|---|
| `anchor` | A member Entity. The rule is evaluated once per row of it. |
| `arguments` | Parameter → path, scalar literal, or list literal. |
| `message` | Optional override (§5.6). |
| `enforcement` | `application` (default) or `database`; locked to `application` when the Validator is non-deterministic (§5.7). |

A **path** is a route rooted at the anchor:

- every segment except the last must be a **reference slot**;
- the last must be a **value slot**;
- **maximum four segments**;
- **every Entity along the path must be a member of the Schema.**

The membership rule holds because membership is explicit: when a path needs a
non-member, the fix is to add it. It buys a real guarantee — a Schema's rules
never reach outside the Schema, so a Schema is self-contained and exportable as a
unit. §9.2's closure-on-add makes this cheap in practice: by the time a Schema is
closed, every path target is already a member.

```
order.customer.country_code       valid — 2 hops, ends on a value slot
product.origin_country            valid — 1 hop
order.customer                    invalid — ends on a reference slot
a.b.c.d.e                         invalid — exceeds four segments
```

Each hop is a join in whatever enforces the rule; the path editor stops offering
reference slots at the fourth segment.

### 9.4 Enforceability

Schema validators are **not expressible as CHECK constraints** — SQL CHECK may
not reference another table. Enforcement means a trigger, a materialized
denormalized column with a CHECK, or application code.

Designer records the rule regardless, but must not imply the database will
enforce it. Hence `enforcement`. `database` means "generate a trigger on export";
`[V2]` v1 stores the flag and notes that nothing generates it. A non-deterministic
Validator locks the flag to `application` (§5.7).

### 9.5 Schemas and export

A Schema is the **export unit**: one Schema, one database or SQL namespace.

Since membership is non-exclusive, the same Entity can be exported into several
databases — legitimate, but a change to one Entity ripples into every Schema
holding it. The Entity form lists its memberships (§13.6) so the blast radius is
visible before an edit.

`[V2]` **Schema composition** — a Schema including another, its members being the
union. `members` stays a plain list so this stays possible.

---

## 10. Context

A namespace, arranged in a tree. Every Validator, Type, Property, Entity and
Schema belongs to exactly one Context. BaseTypes and built-in Validators belong
to none and are visible everywhere.

### 10.1 Visibility `[DECIDED]`

An item is visible from Context C if it belongs to C **or to any ancestor of C**.

The "show only this Context" flag is a **filter on the browser lists** only. It
does not change reference resolution.

- Sibling contexts are never visible to each other.
- Shadowing: the nearer name wins; the tool warns on a shadowing name. An
  authored Validator may shadow a built-in, which resolves in its favour and
  warns — the qualified naming in §5.3 is what keeps such a case legible.
- Moving an item between Contexts is allowed only if every referencing item can
  still see it at the new location. This includes Schemas: moving an Entity
  deeper can put it out of reach of a Schema listing it, so the move is refused
  with those Schemas named.

| | Context | Schema |
|---|---|---|
| Shape | Hierarchical | Flat |
| Membership | Exclusive — one item, one Context | Non-exclusive, explicit |
| Governs | What an item can *reach* | What a deliverable *contains* |
| Applies to | Every kind of item | Concrete Entities only |
| Changes when | An item is moved | Someone adds or removes a member |

---

## 11. Deleting `[DECIDED]`

**No delete is refused.** Every delete shows an impact dialog, and the user
decides. Built-ins cannot be deleted at all (§5.7).

Once the model is designed to hold incomplete states and describe them, a
dangling reference is a diagnostic rather than a corruption, and refusing the
delete only forces the user to dismantle references by hand for the same end
state.

### 11.1 The impact dialog

It lists what will change, grouped by consequence rather than by referencing
item, because "17 items reference this" is not a decision aid and "3 Schemas lose
a member, 2 slots lose their target" is. Every affected item is named per §5.3.

The delete planner returns a tuple of **`Consequence`** records — its own type,
sharing the diagnostic's locator but not its shape, since a consequence predicts
what would happen while a diagnostic describes what is true (appendix
*diagnostics* §11). The same tuple renders the dialog and, on confirmation,
drives the fixups, so what the user was shown and what happens are computed once
rather than twice.

| Reference to the deleted item | Consequence |
|---|---|
| Schema membership | Member removed. The Schema stays valid, though it may become unclosed (§9.2). |
| Reference slot `target` | Target set null; the slot becomes `incomplete`. |
| Type `parent` | Parent set null; the Type becomes `incomplete`. |
| Property `type` | Type set null; the Property becomes `incomplete`. |
| Value slot `property` | Property set null; the slot becomes `incomplete`. |
| Entity `extends` | Extension cleared. **The descendant loses every inherited slot**, and any narrowing override it declared now overrides nothing — an error. The most destructive case; the dialog says so explicitly. |
| Validator in a binding | The binding is removed entirely. A binding without a validator has no meaning. |
| **Validator used as a composite operand** | **The UUID is left in the expression text**, which becomes an unresolved-operand error. Designer does not rewrite the expression, because removing an operand from `A AND B` changes what the rule means, and only the author can decide what it should become. |
| Schema validator `anchor` | The anchor is cleared; the rule becomes `incomplete`. |

The composite-operand row is the one case where the deletion leaves *text* rather
than a null — a direct consequence of storing operands as UUIDs, and deliberate:
the damage stays visible and attributable rather than silently repaired.

### 11.2 Delete is one command

The whole delete — the item, every nulled reference, every removed membership,
every dropped binding — is **a single command**. If the fixups were separate, one
Ctrl-Z would bring back the Entity with its references still broken, which is
worse than either state. The rule generalises: **a single user action is a single
command, however many objects it touches** (§13.8).

### 11.3 Recursive Context delete

Deleting a Context deletes its subtree — child Contexts and all items within,
including Schemas defined there. The confirmation shows the **JSON subtree about
to be removed**, a count by kind, and the same impact table as §11.1 for every
reference from outside. Likewise one command.

### 11.4 Undo stack `[DECIDED]`

**Capped at 100 commands**, oldest dropped, because a single delete command can
hold an entire Context subtree and an uncapped stack has no bound on memory.

The value is a settings key from v1 (§14.3) with a default of 100, so `[V2]` a
**Preferences** dialog can expose it without a file-format change.

### 11.5 What undo does not cover

- **The undo stack does not survive a restart or a crash.** Autosave (§12.1)
  writes after every command, so a crash following a delete recovers the
  post-delete state with no history to undo it.
- The 100-command cap adds a second edge: a delete more than 100 actions ago is
  no longer undoable within the session either.
- Mitigation, cheap and standard: on **Save**, move the previous file content to
  `<name>.json.bak`, one generation. That covers both edges.
- `[V2]` The command journal (§12.1) supersedes the `.bak` file rather than
  complementing it.

### 11.6 Model check

Three severities — `error`, `warning`, `incomplete` — plus informational notes.
`incomplete` never blocks saving (§3.1).

Severity, title and message belong to the **code**, not to the finding: a
diagnostic instance carries only its code, a locator, an optional span and its
arguments, and everything human-facing is looked up in the code registry
(appendix *diagnostics* §5). Export gating is declarative, through `blocks_export`
on the code definition, rather than a list of special cases inside the exporter —
which is why "Schema not closed" can stay a `warning` at all times and still stop
an export.

Each code also declares a **scope** — `item`, `context` or `model` — so the
re-check after every command (§13.8) is neither wrong nor whole-model. Without it
a rename would miss the duplicate-name finding on the *other* item, since that
item did not change. `model`-scope rules run on demand and before export.

The findings, by severity:

**Incomplete** — unset Type parent, unset Property type, unset slot Property or
target, unset validator anchor, blank names, bindings whose type cannot resolve.

**Errors** — dangling references; Type parent cycles, Entity extension cycles,
Validator cycles; expression parse failures; unresolved or deleted composite
operands; **a built-in referenced by UUID that this library version does not
have**, naming the required version (§5.7); binding type errors, including
non-homogeneous or mistyped list literals (§5.6); a narrowing override whose
inherited slot no longer exists; abstract Entity as a Schema member; Schema
member not visible from the Schema's Context; Schema validator anchor that is not
a member; path entity that is not a member; unresolvable paths, paths ending on a
reference slot, paths exceeding four segments; Entity validator bound to a
reference slot; reference slot targeting an abstract Entity or one without
identity; slot overrides that widen; `set_null` on a required slot; duplicate
names.

**Warnings** — Schema not closed, naming each outward reference; **a Type or
Entity binding to a non-deterministic Validator**, which no CHECK constraint can
carry (§5.7); shadowing, including an authored Validator shadowing a built-in;
reference slot whose target has concrete descendants; abstract Entity with no
concrete descendant.

**Informational** — `enforcement = database` generates nothing yet; use of a
deprecated built-in; concrete Entities in no Schema; Schemas with fewer than two
members; orphaned items.

Two Schemas sharing a member is **not** reported, nor are Entity reference cycles.

---

## 12. Persistence `[DECIDED]`

**v1: a single JSON document per model.** Diffs well in git, loads whole, no
dependency.

A flat list per kind, every item keyed by UUID, every reference stored as a UUID
string. Do not nest — the model is a graph.

Non-native literals per §4.1; list literals as JSON arrays of those forms.
**Expressions are stored as source text**, with composite operands as UUIDs
inside that text (§5.2). Paths are stored as ordered lists of slot UUIDs, and
**bindings carry their own UUID** — both because a diagnostic or a consequence
addresses list elements by identity rather than by index, which would go stale on
any reorder.
**Schema membership is stored** as a list of Entity UUIDs. **Built-in Validators
are not stored** — only references to them. Every reference field is **nullable**.

The file carries two integers: **`schema_version`** for the format and
**`library_version`** for the standard library it was authored against (§5.7).
Both are independent of the package version (§14.1).

The same flat-per-item JSON shape serves the editor's JSON tab, the
recursive-delete preview and the autosave file. The JSON tab therefore shows
composite expressions in their **stored** UUID form, which is a fair trade — it
is a debugging view, and the display form would hide exactly what someone opening
it wants to see.

### 12.1 Autosave and crash recovery `[DECIDED]`

After every committed command, the whole model is written to an autosave file.

- **Debounced** ~250 ms after the last command.
- **Atomic**: write to `<name>.tmp`, then `os.replace()` — atomic on POSIX and
  Windows, where a plain write is not. A crash mid-write would otherwise leave a
  truncated recovery file, the one file that must never be corrupt.
- **Location**: the application state directory (§14.3).
- **Content**: the model, the path of the file it belongs to (null if never
  saved), and a timestamp.
- **Lifecycle**: removed on successful save and on clean exit, so its presence at
  startup means the last session did not end cleanly.
- **Recovery** is offered at startup before anything else opens (§14.4).

Limits: the undo stack is not persisted (§11.5), and serialising the whole model
per commit is fine at human editing speed for models of a few thousand items.
`[V2]` A command journal fixes both.

`[V2]` A SQLAlchemy-backed store for the catalogue itself, behind the repository
interface (`load`, `save`, `items_in_context`, `references_to`).

---

## 13. Application

### 13.1 Window `[DECIDED]`

- Menu bar, central area, status line.
- Opens maximised. No portable call exists: `state("zoomed")` on Windows,
  `attributes("-zoomed", True)` on X11, geometry from `winfo_screenwidth` /
  `winfo_screenheight` on macOS.
- **Minimum window size 1024 × 768** via `root.minsize`, clamped to the screen if
  the display is smaller.
- The editor pane has its own minimum height.
- **Single-document, single-window.**

### 13.2 Layout `[DECIDED]` — six columns

A vertical `ttk.PanedWindow` with two panes:

- **Upper** — a horizontal `ttk.PanedWindow` with six children, left to right:
  **Context, Validator, Type, Property, Entity, Schema** `[CHANGED]`. Validator
  moved ahead of Type: a Type is built from Validators, and a Validator depends
  on nothing but the base types, so the order is now strictly what things are
  made of before what is made from them.
- **Lower** — the editor.

`ttk.Treeview` throughout: hierarchical for Context, Type and Entity, flat for
Schema, Property and Validator. One code path, sortable headings for free.

The **Entity column is an extension tree**, with abstract Entities in a distinct
style. Each column has a filter entry above its list.

The **Validator column** also shows built-ins, in a distinct style, visible from
every Context. Its filter carries a **show built-ins** toggle, defaulting to off
once a model has validators of its own — forty built-ins swamping a user's five
would make the column useless. Deprecated built-ins are marked and hidden from
pickers.

### 13.3 Column widths and collapsing `[DECIDED]`

**Ten 'm' is the minimum column width**, measured at runtime with
`tkinter.font.Font.measure("m") * 10` on the actual UI font so the rule follows
font size and DPI scaling. Designer is not a small-screen application; the
1024 × 768 floor stands.

**Manual collapse only.** Automatic collapse is deferred (§15), which removes
pinning, resize monitoring, the `<Configure>` debounce, the collapse priority
order and one settings key along with it.

- A slim toolbar above the upper pane with six toggle buttons.
- Collapsing calls `PanedWindow.forget(pane)`; restoring calls `insert(index,
  pane)` at the remembered position. Driving a sash to zero instead leaves a dead
  draggable strip that fights the next resize.
- Each pane's last width is remembered.
- **Reset layout** restores all six at their default widths.

### 13.4 Context breadcrumb `[DECIDED]`

A breadcrumb at the top of the editor pane: `root › billing › invoicing`.

It exists because the Context selection filters every other column and determines
where a new item is created; with the Context column collapsed it is the only
indicator of both.

- Each segment is clickable and switches the active Context to that ancestor.
- The final segment carries a dropdown listing child Contexts and siblings.
- Always visible, whether or not the Context column is.

### 13.5 Path editor

A cascading selector rooted at the anchor offers, at each step, only that
Entity's slots: reference slots continue the path, value slots end it, and
reference slots stop being offered at four segments (§9.3).

Non-member targets are **shown but marked**, and choosing one prompts to add it
to the Schema — running the same closure check as any other add (§9.2). Hiding
them would leave the user unable to see why the path they wanted is unavailable.

### 13.6 Editor pane `[DECIDED]` — generated form, plus a JSON tab

Below the breadcrumb, a notebook with two tabs.

**Form tab.** Generated per kind. Common controls: `name`, `description`, and
read-only `uuid`, `created`, `modified`.

| Kind | Kind-specific editor |
|---|---|
| Context | parent selector |
| Schema | member list with add/remove; **Add missing referenced entities**; closure status; cross-entity binding list with anchor picker, path editor and `enforcement` flag |
| Entity | `abstract` checkbox; `extends` picker; slot table; binding list; identity; indexes; default order; read-only list of Schemas this Entity belongs to |
| Property | Type picker |
| Type | parent picker; binding list |
| Validator | leaf/composite switch; parameter list; expression `Text`; message |

**Binding rows**, in all three forms, show the inferred BaseType beside each
argument, flag §5.6 findings inline, offer the **message override** field, and —
for a list argument — an editable list of values rather than a text field. A
binding to a non-deterministic Validator shows its `enforcement` locked, with the
reason (§5.7).

**Built-in Validators** open in a read-only form with a **Fork to model** action.
Non-deterministic ones are marked, with the reason.

The **Validator form** shows a composite's expression in display form, with
operand names rather than UUIDs (§5.2), and an operand picker that inserts a
Validator visible in scope — including built-ins.

The Schema member picker offers concrete Entities **visible from the Schema's
Context**, with members marked. Closure status is either "closed" or a count of
dangling references with the fix button beside it.

The **slot table** is the most complex control in the application and the main
build risk. It shows inherited slots read-only above the Entity's own, and offers
an override action on an inherited row that creates a narrowing slot (§8.1)
rather than a duplicate, with its Type picker filtered to narrowing Types.

**JSON tab.** Read-only in v1, showing the selected item in the on-disk shape,
with a copy button. `[V2]` Editable once the form editor settles.

### 13.7 Column linkage `[DECIDED]` — hybrid

- The Context selection **filters** all five other columns.
- The Schema selection **filters** the Entity column to its members, and through
  it the Property column.
- Selecting an Entity **highlights** its Properties; a Property highlights its
  Type; a Type highlights its Validators.
- Selecting an Entity also **highlights the Schemas it belongs to**, and the
  Entities it references, in a colour distinct from the extension relationship.
- `[CHANGED]` A **follow selection** toggle switching highlighting to filtering
  was specified here, built, and then removed. In use it reduced a fourteen-row
  Type column to the single row it had already highlighted — no new
  information, and no way left to compare or switch. Highlighting stands on its
  own; what the toggle was reaching for, finding a related row below the fold,
  is served by scrolling to it instead.

### 13.8 Editing, commands and undo `[DECIDED]`

**One user action is one undo step.** Not one object, not one field — one
intention. Editing three slot rows is three steps; adding a member with its
closure is one; a delete with a dozen fixups is one.

The editor is **live**:

- **Structured controls commit immediately** — checkboxes, pickers, list add,
  remove and reorder, slot rows, bindings, schema membership.
- **Free-text fields commit on focus-out or Enter** — `name`, `description`,
  `expression`, `message`. One command per field per commit, not per keystroke.

Apply and Revert are gone; undo replaces Revert, and there is no unsaved-edits
prompt on selection change, because nothing is ever pending.

**One undo stack.** The expression `Text` widget is created with `undo=False`.
Ctrl-Z means the same thing everywhere. Two things follow:

- **Escape reverts the focused field** to its last committed value.
- **Validation reports; it does not block the commit.** An invalid edit cannot be
  refused without contradicting §3.1 — the user would be trapped in the field,
  unable to change selection or save. So the field commits, the checker runs, and
  errors show inline and in the model check.

The command stack holds objects with `do` and `undo`, capped per §11.4. Every
mutation goes through it. Each command triggers a debounced autosave and an
incremental re-check of the affected items.

### 13.9 Actions

Each column carries a toolbar: **New**, **Duplicate**, **Delete**, mirrored on a
right-click menu and the Edit menu. Delete opens the impact dialog (§11.1).

**New creates an empty item** in the active Context and selects it, with focus in
the name field. Duplicate copies every field except `uuid`, `created` and `name`,
left blank so the user names it deliberately. Duplicating a Schema copies its
member list; duplicating a composite Validator copies its expression, operand
UUIDs and all. On a built-in, Duplicate is **Fork to model** (§5.7).

### 13.10 Status line

Selected item's kind and name, model dirty state, and the last model check
result. The Context path lives in the breadcrumb.

---

## 14. Packaging and runtime `[DECIDED]`

### 14.1 Two distributions, one repository

| Package | Contents | Dependencies |
|---|---|---|
| `designer-model` | Domain items, expressions module, path resolver, model check, JSON persistence, repository interface, **the standard library JSON fragment as package data** | **Standard library only** |
| `designer-app` | tkinter UI, application state, layout | `designer-model` |

The domain model goes to PyPI so later tools depend on it without a GUI, and it
carries the validator library with it — a generator or CLI needs the same
built-ins the UI does. **`designer-model` must never import tkinter**, and a test
asserts it.

Layout: `packages/designer-model/` and `packages/designer-app/`, each `src/`
layout with its own `pyproject.toml`.

Three version numbers, deliberately uncoupled: the package version (semver), the
model file `schema_version`, and `library_version`.

### 14.2 Python and tooling

- **Python 3.12** `[CHANGED]`. The floor was 3.14, the current release at the
  time; it is now 3.12, which is what the code is developed and run on.
  Nothing in the codebase needs anything newer, and a floor above the
  interpreter in use is not a floor — it let ruff introduce PEP 758 syntax
  that the running interpreter rejected. `requires-python`, ruff's target
  and mypy's `python_version` are one number, stated once.
- **ruff** for lint and format over every Python file. `line-length = 120`,
  4-space indent.
- ruff will flag the `eval` in the expressions module (S307). Suppress it there,
  with a comment pointing at §5.4.
- **pytest**. The domain package's tests run headless. The standard library ships
  **passing and failing example values with each built-in**, so the whole library
  is asserted by one parameterised test — the cheapest guard against the bug this
  library is most prone to, a regex that is subtly wrong in a way no reviewer
  notices. The same fixtures serve the test bench when it arrives.
- **tkinter is standard library but not always installed** — Debian and Ubuntu
  ship it as `python3-tk`. It cannot be declared as a dependency, so
  `designer-app` checks at startup and fails with a message naming the package.

### 14.3 Application state

Per-user config directory: `$XDG_CONFIG_HOME/designer/` or `~/.config/designer/`
on Linux, `%APPDATA%\Designer\` on Windows,
`~/Library/Application Support/Designer/` on macOS.

The standard library has no `platformdirs` equivalent, so this is either a
~20-line resolver or a dependency. **Recommendation: write the resolver**, since
it is the only thing that would otherwise pull one in.

| Key | Default | Exposed in v1 |
|---|---|---|
| `recent_files` | — | File menu |
| `last_file` | — | startup |
| `window_geometry`, `sash_positions`, `column_widths`, `collapsed_columns` | — | layout |
| `follow_selection` | false | toggle |
| `show_builtins` | false | Validator column filter |
| `undo_limit` | 100 | `[V2]` Preferences |
| `autosave_delay_ms` | 250 | `[V2]` Preferences |
| `recent_files_limit` | 10 | `[V2]` Preferences |

A corrupt settings file is replaced with defaults, never fatal.

### 14.4 Startup `[DECIDED]`

1. Load settings; fall back to defaults on any problem.
2. Load the standard library into the read-only registry.
3. **If an autosave exists**, offer recovery before anything opens, naming the
   file it belongs to and its timestamp. Declining discards it.
4. Otherwise, **reopen the last file** if settings name one and it loads.
5. Otherwise, start with an **empty model**.

Reopening must never prevent startup. Missing, unreadable, or a newer
`schema_version` gives an empty model plus a non-modal notice. A newer
`library_version` opens normally; unresolvable built-ins become named errors
(§11.6).

**Recent files** are capped by `recent_files_limit`, most-recent-first,
deduplicated by resolved absolute path. An entry whose file is missing is **kept
and marked unavailable** rather than dropped.

`[V2]` A sample model, shipped as a file to open.

---

## 15. Deferred `[V2]`

- **Test bench** — enter sample values, see which validators pass or fail and
  why, evaluated off the UI thread so a pathological regex cannot hang the
  window. Worth pulling into v1 if anything else can be dropped.
- **Preferences dialog**, exposing `undo_limit`, `autosave_delay_ms` and
  `recent_files_limit`.
- **Automatic column collapse** (§13.3), which would reintroduce pinning.
- **Schema composition** — a Schema including another (§9.5).
- Command journal replacing snapshot autosave, giving persistent undo (§12.1).
- Trigger generation for `enforcement = database` Schema validators (§9.4).
- Per-chain joined-table inheritance for polymorphic references (§8.2).
- Scalar union types (§8.2).
- Collections (§8.4).
- Editable JSON tab (§13.6).
- SQLAlchemy-backed model store (§12).
- Export: DDL, SQLAlchemy declarative classes, or Pydantic models, one Schema at
  a time.
- A sample model file (§14.4).
- Multi-model library import.

---

## 16. Status

**All four pre-build gaps are closed.** The specification and its three
appendices — the validator library, the signature table, and the diagnostics —
are accepted in full, and nothing in any of them is open.

One deliverable remains before the domain model is written, and it is a piece of
work rather than a decision:

**A second worked example.** The standard library fragment (§5.7) exercises the
file format for Validators thoroughly and nothing else. A small companion example
covering Entities, slots, extension, a Schema with membership and a cross-entity
rule with a path would exercise the decisions most likely to be wrong in practice
— nullable references, stored slot-UUID paths, binding UUIDs, and an
intentionally incomplete item. Writing it before the domain model means the first
tests have something real to load, rather than fixtures invented alongside the
code they are meant to check.

After that, phase 1 — domain model, persistence and model check, headless and
test-driven — has everything it needs.
