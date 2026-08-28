# Designer — Specification (revision 8)

Original: 27 August 2026. Revised: 28 August 2026.

Markers:

- `[DECIDED]` — settled in review; recorded with its consequence.
- `[OPEN]` — still to decide. None block starting work.
- `[V2]` — deliberately deferred.

---

## 1. Purpose

Designer is a desktop tool for authoring and browsing a **data model**: a
catalogue of reusable validation rules, type definitions, fields, record
structures and the schemas that group them, organised into namespaces.

The tool edits the model itself. It does not execute the model against real data
(see §14, test bench).

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
| Binding | The attachment of a Validator to a Type, Entity or Schema, with its arguments supplied. |
| Path | A route from an anchor Entity through reference slots to a value slot (§9.2). |
| Abstract Entity | A modelling-only Entity that never becomes a table. |
| Concrete Entity | An Entity that materializes as one flattened table. |
| Context | A modelling namespace controlling visibility. Hierarchical. |
| Schema root | A Context that hosts a Schema. |
| Schema | The concrete Entities of one Context subtree, plus the rules spanning them. |

---

## 3. Common item structure

Every item, **including Context and Schema**, has:

| Field | Type | Notes |
|---|---|---|
| `uuid` | UUID | Immutable. All references use this, never the name. |
| `name` | string | Must match `[A-Za-z_][A-Za-z0-9_]*`. Unique per (Context, kind). |
| `description` | string | Free text, may be empty. |
| `created` | timestamp | Set once, UTC. |
| `modified` | timestamp | Updated on change to the item's own fields only. Does not propagate to referencing items. |

Renaming never breaks references, because references are by UUID.

---

## 4. BaseType `[DECIDED]`

Eight fixed, built-in scalar types, not editable by the user:

| BaseType | Notes |
|---|---|
| `integer` | |
| `real` | Binary floating point. |
| `decimal` | Exact. Never mixes with `real` (§5.5). |
| `boolean` | |
| `string` | |
| `datetime` | Timezone-aware, always UTC (§4.2). |
| `date` | No time component, no zone. |
| `time` | No date component, no zone. Comparison only (§4.3). |

`null` is **not** a BaseType. Optionality belongs to the slot, as `required`
(§7.2). Consequence: a Type always describes a present value.

BaseTypes are global, have no Context, and are the roots of the Type hierarchy.

### 4.1 Literals

Defaults and validator arguments of the non-JSON-native types are stored as
tagged strings, never as JSON numbers or bare strings:

| BaseType | Storage form |
|---|---|
| `decimal` | Decimal string. A JSON number would silently round. |
| `datetime` | ISO-8601 with a `Z` suffix: `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` |
| `date` | ISO-8601, `YYYY-MM-DD` |
| `time` | ISO-8601, `HH:MM:SS[.ffffff]` |

### 4.2 Timezone policy `[DECIDED]`

`datetime` is **timezone-aware and always UTC**, serialised with a `Z` suffix.

- A naive `datetime` literal is rejected on entry and on load.
- A literal with a non-UTC offset is normalised to UTC on entry; the original
  offset is not retained.
- Export maps `datetime` to `timestamptz`, not `timestamp`.
- Two `datetime` values are therefore always comparable, which is what makes the
  §5.5 signature table total for this type.

`date` and `time` remain zone-free, because a calendar date and a wall-clock time
are not instants. This is why `date` and `datetime` may not be compared without
an explicit conversion: the conversion depends on a zone that neither value
carries.

### 4.3 `time` arithmetic `[DECIDED]`

`time` supports **comparison only**. `time − time`, `time + duration` and
`time − duration` are all static errors.

Wrapping at midnight would quietly turn 23:00 + 2h into 01:00, which is almost
never the intent, and the honest fix for anyone wanting that behaviour is to
model a duration rather than a wall-clock time.

`duration` still arises, from `datetime − datetime` and `date − date` (§5.5).

---

## 5. Validator

A named, reusable predicate.

### 5.1 Leaf and composite

A Validator is **either** a leaf or a composite, never both.

**Leaf**

| Field | Notes |
|---|---|
| `parameters` | Ordered list of parameter names. May be empty. |
| `expression` | Predicate source, returning boolean. |
| `message` | Shown when the predicate returns false. May interpolate parameters: `"at most {max}, got {value}"`. |

An empty `parameters` list means the expression uses a single implicit argument
named `value`.

**Composite**

| Field | Notes |
|---|---|
| `parameters` | Union of what the operands need. |
| `expression` | Boolean expression over *references to other Validators*, using `AND`, `OR`, `XOR`, `NOT` and parentheses. |
| `message` | Optional; see §5.4. |

The composite is stored as a parsed expression tree. A flat collection cannot
represent `A AND (B OR C)`.

**Validators are not typed.** A Validator declares parameter *names*, not
parameter BaseTypes, so `between(min, max)` serves `integer`, `decimal`, `date`
and `datetime` alike. A Validator has no value type of its own; types are known
only at the **binding** (§5.5).

### 5.2 Expression evaluation `[DECIDED]`

**Composite expressions get a dedicated parser, now.** The grammar is
identifiers, `AND` / `OR` / `XOR` / `NOT`, and parentheses — recursive descent,
roughly 80 lines. Python `eval` is wrong here: `and` and `or` short-circuit and
return operands rather than booleans, and Python has no `xor` keyword, so the
semantics would be quietly wrong for exactly the operators specified.

**Leaf expressions are evaluated with `eval` for v1**, but parsed and type-checked
first (§5.5). All expression handling goes through one `expressions` module
exposing `parse`, `check` and `evaluate`. Nothing else in the codebase calls
`eval` or `compile`.

Since the static checker already walks the `ast.parse` tree of every leaf
expression, the whitelist visitor that turns `eval` into a sandbox is the same
walk with a rejection list attached. Both are v1, built together.

### 5.3 Constraints

- A Validator must not reference itself, directly or transitively.
- A composite's operands must be resolvable in its scope (§10).

### 5.4 Failure messages

If a composite has its own `message`, report only that. Otherwise report the
operands that contributed to the failure — for `AND`, the failing operands; for
`OR`, all of them, since all failed; for `NOT`, a negated form.

### 5.5 Static type checking of bindings `[DECIDED]`

Every binding of a Validator is type-checked when the binding is made, and again
in the model check. Three binding sites:

- **Type → Validator.** The value's BaseType comes from the Type's parent chain.
- **Entity → Validator.** Each parameter binds to a **value slot** (§7.2).
- **Schema → Validator.** Each parameter binds to a **path** from an anchor
  Entity; the path resolves to a BaseType (§9.2).

The check applies to all three and not just the cross-field cases, because a
Validator is reusable across many Types: a leaf expression sound for the Type it
was written against can be nonsense for the next Type that attaches it. The
mismatch is a property of the binding, never of the Validator alone.

**The checker.** Given the expression AST and a map from parameter name to
BaseType, it infers a type for every node and reports:

- mixed `decimal` and `real` in arithmetic — error;
- comparison between incompatible BaseTypes — error;
- `date` compared with `datetime` — error, conversion must be explicit (§4.2);
- any arithmetic on `time` — error (§4.3);
- a top-level result that is not `boolean` — error;
- any parameter never used in the expression — warning.

**The internal type lattice is larger than the BaseType set.** Subtracting two
`datetime` or two `date` values yields a duration, a legitimate intermediate
value and not a BaseType. The checker carries an internal `duration` type usable
only inside an expression: comparable with another duration, addable to a
`datetime` or `date`, but never the type of a slot, a Property, or a top-level
result.

**Operator signatures** (abbreviated; the full table lives with the checker):

| Operation | Result |
|---|---|
| `integer` ∘ `integer` | `integer`; `/` gives `real` |
| `integer` ∘ `real` | `real` |
| `integer` ∘ `decimal` | `decimal` |
| `real` ∘ `decimal` | **error** |
| `string` + `string` | `string` |
| `datetime` − `datetime`, `date` − `date` | `duration` |
| `datetime` ± `duration`, `date` ± `duration` | `datetime`, `date` |
| any arithmetic on `time` | **error** |
| comparisons on any two compatible types above | `boolean` |
| `len(string)` | `integer` |

Integer-with-decimal widening is allowed deliberately, so `price <= 100` needs no
ceremony. Real-with-decimal is not, because that is the one that silently
destroys exactness.

---

## 6. Type

A named restriction of a BaseType.

| Field | Notes |
|---|---|
| `parent` | Reference to a BaseType or another Type. Exactly one. |
| `validators` | Ordered list of (Validator reference + argument bindings). |

The **effective validator set** is the parent's effective set followed by this
Type's own. Validation is conjunctive.

The **base type** is derived from the parent chain, not stored. Every chain
terminates at exactly one BaseType. The chain must be acyclic; enforced at save.

Argument binding: if a Validator declares parameters, the Type must supply each —
a literal (`max = 255`) or the implicit `value`. Each binding is type-checked per
§5.5 against the Type's derived BaseType.

**Type narrowing.** Type `B` narrows Type `A` when `A` appears in `B`'s parent
chain. Both then share a BaseType, and `B`'s effective validator set is a
superset of `A`'s, so any value valid for `B` is valid for `A`. A cheap chain
walk, and §8.1 depends on it.

Structural recursion is not a Type concern. A self-referential model
(`Employee.manager → Employee`) uses an entity reference, §8.3.

---

## 7. Property and Slot

### 7.1 Property `[DECIDED]`

A Property is a **shared, reusable field definition** — one Property, referenced
by many Entities. `customer_id` is defined once.

| Field | Notes |
|---|---|
| `type` | Reference to a Type or BaseType. |

Consequence: nothing that varies per use may live on the Property. Required,
default and position are per-Entity facts and live on the Slot.

### 7.2 Slot

The use of something inside one Entity. Not a top-level item, no column of its
own, edited in the Entity form.

| Field | Notes |
|---|---|
| `slot_name` | Defaults to the Property or Entity name; overridable, so one Entity can hold two references to the same target (`author`, `reviewer`). |
| `kind` | `value` or `reference`. |
| `required` | Boolean. Maps to `NOT NULL`. |
| `position` | Ordinal within the Entity. |

A **value slot** additionally has `property` (reference to a Property), an
optional `default` literal, and an optional `type_override` (§8.1). Its BaseType,
needed by §5.5, comes from the Property's Type chain, or the override's.

A **reference slot** is described in §8.3.

`[DECIDED]` **Entity validators bind to value slots only.** A reference slot has
no scalar value to test — it denotes a row in another table. Reference slots
appear in Schema validators, but only as *navigation*, never as the final term of
a path (§9.2).

---

## 8. Entity

A record structure.

| Field | Notes |
|---|---|
| `abstract` | Boolean. See §8.1. |
| `extends` | Optional reference to another Entity. Single inheritance. |
| `slots` | Ordered list of Slots. |
| `validators` | Optional list of (Validator reference + bindings), where bindings name **value slots** of this Entity. Row-local rules such as `start_date < end_date`. Type-checked per §5.5. |
| `identity` | Optional list of slots forming the primary key. |
| `indexes` | List of (slot list, `unique` flag). |
| `default_order` | List of (slot, ascending) pairs. |

Entity validators are **row-local**: every parameter resolves within one row of
this Entity, so the rule maps directly onto a CHECK constraint. Rules that span
tables live on a Schema (§9).

Indexes and ordering are structured lists, not expressions. An expression cannot
be mapped onto a real index by any backing store.

### 8.1 Extension, abstraction and narrowing `[DECIDED]`

Single inheritance. The chain must be acyclic.

**Effective slots** = the parent's effective slots, then this Entity's own.
**Effective validators** = the parent's, then this Entity's, conjunctive.

**Abstract Entities.** An Entity marked `abstract` is a modelling device only. It
never becomes a table. It exists to factor shared slots and validators out of
several concrete Entities. Rules:

- An abstract Entity may not be the target of a reference slot (§8.3). There is
  no table to point a foreign key at.
- An abstract Entity may declare `identity` and `indexes`; each concrete
  descendant materializes them on its own table.
- An abstract Entity with no concrete descendant is a warning, not an error.
- An abstract Entity is never a Schema member (§9.1).

**Materialization is flattened.** Each concrete Entity becomes exactly one table
containing all of its effective slots as real columns, inherited ones copied in.
This is concrete-table inheritance; §8.2 covers what it costs.

**Slot narrowing.** A descendant may redeclare an inherited `slot_name`, subject
to:

- The slot kind may not change.
- For a value slot, `type_override` must name a Type that narrows the inherited
  one in the sense of §6. Widening is rejected.
- `required` may go false → true. Not true → false.
- `default` may be replaced, and must satisfy the narrowed Type.
- A **reference slot's target may not be narrowed.** Changing the target changes
  which table the foreign key points at — a different column, not a restriction
  of the same one. `required` may still be narrowed.

Because each concrete table is flat, a narrowed slot's constraints are simply the
constraints emitted on that table's own column. No cross-table CHECK is needed —
precisely why narrowing works here and would not under joined-table inheritance.

**Identity** is inherited when an ancestor declares it. A descendant may declare
`identity` only if no ancestor did.

### 8.2 Extension does not give polymorphic references

Revision 3 claimed extension substitutes for union types: a reference to
`Vehicle` meaning "a Car or a Truck". **Flattened materialization withdraws that
claim**, and the trade was made knowingly when narrowing was chosen.

With one flat table per concrete Entity there is no shared `Vehicle` table for a
foreign key to target. So:

- A reference to an **abstract** Entity is rejected outright (§8.1).
- A reference to a **concrete** Entity that has concrete descendants reaches only
  that Entity's own rows, never its descendants'. The model check warns; it is
  legal but almost never what the modeller means.

In practice: use extension with an abstract base to factor shared structure, and
keep concrete Entities as leaves.

`[V2]` If genuine polymorphic references become necessary, the tractable route is
joined-table inheritance for the specific chain that needs it, which would forbid
narrowing on that chain. A per-chain choice, not a global one.

Scalar unions stay out. `[V2]` No mainstream relational database has a sum type.

### 8.3 Entity references `[DECIDED]`

A reference slot has:

| Field | Notes |
|---|---|
| `target` | Reference to a **concrete** Entity. |
| `inverse_name` | Optional name for the reverse accessor, for ORM generation. |
| `on_delete` | `restrict` / `cascade` / `set_null`. `set_null` requires `required = false`. |

Rules:

- The target must be concrete and must have an identity, declared or inherited.
- The target must be **visible** from this Entity's Context (§10). It need not be
  in the same Schema — references cross Schema boundaries freely (§9.2).
- **To-one only.** See §8.4.
- Reference cycles are allowed, including self-reference. This is the recursion
  the Type system deliberately does not carry.
- `required` maps to `NOT NULL` on the foreign key.

### 8.4 Collections `[V2]`

Deferred, at close to zero cost for a relational model:

- **One-to-many** is modelled from the child side, as a to-one reference on the
  child.
- **Many-to-many** is an explicit join Entity holding two references.

---

## 9. Schema

A **Schema** is the set of concrete Entities in one Context subtree, plus the
rules that span more than one of them.

| Field | Notes |
|---|---|
| `validators` | Cross-entity validator bindings (§9.2). |

A Schema has no membership list. Its members are derived from the Context it
belongs to.

### 9.1 Membership is derived and exclusive `[DECIDED]`

A Schema belongs to a Context like any other item (§3). That Context is its
**schema root**, and the Schema's members are every concrete Entity whose own
Context is the root or a descendant of it.

- **At most one Schema per Context.** Two Schemas in one Context would have
  identical membership.
- **A schema root's subtree may not contain another schema root.** This is the
  rule that makes membership genuinely exclusive: without it, an Entity in
  `billing/invoicing` would belong to both the `billing` Schema and the
  `invoicing` one. With it, the schema roots partition the Context tree and every
  concrete Entity belongs to at most one Schema.
- **Abstract Entities are never members**, since they never materialize and have
  no rows for a rule to range over. Their concrete descendants are members if
  their Contexts fall in the subtree.
- A concrete Entity in no schema root's subtree belongs to no Schema. Legal, and
  reported as informational — it is the normal state during modelling.

Membership is **live**: moving an Entity between Contexts can move it between
Schemas, or out of all of them. The Context move confirmation says so, and the
model check catches rules left dangling by the move.

Because membership now partitions the tree, a Schema is the natural **export
unit** — one Schema, one database or SQL namespace — with no shared-member case
to warn about.

Note what this deliberately gives up: a `Customer` shared by two lines of
business cannot be a member of both Schemas. It lives in one subtree, and the
other Schema reaches it by *reference*, not by membership (§9.2).

### 9.2 Cross-entity validators and anchored paths `[DECIDED]`

`entity.property` on its own does not define a rule. `Order.total` and
`Invoice.total` name two columns in two tables, but a predicate over them has no
meaning until something says **which Order row pairs with which Invoice row**. A
row-local Entity validator has an implicit answer — the row it is checking. A
cross-entity rule has none.

So a Schema validator binding carries an **anchor** and **paths**:

| Field | Notes |
|---|---|
| `anchor` | An Entity that is a **member of this Schema**. The rule is evaluated once per row of it. |
| `bindings` | Parameter name → path, or → literal. |
| `enforcement` | `application` (default) or `database`. See §9.3. |

A **path** is a route rooted at the anchor:

- every segment except the last must be a **reference slot**;
- the last segment must be a **value slot**;
- the path's BaseType is that value slot's, feeding §5.5 unchanged;
- **maximum four segments**, i.e. at most three reference hops before the value;
- every Entity along the path must be **visible from the Schema's Context**.

**A path may leave the Schema.** Only the anchor must be a member. This rule
changed when membership became exclusive: with a shared `Customer` necessarily
living outside most Schemas' subtrees, requiring every hop to be a member would
make the majority of useful rules illegal. Membership defines what a rule ranges
*over*; visibility defines what it can *reach*.

With anchor `OrderLine`:

```
order.customer.country_code       valid — 2 hops, ends on a value slot
product.origin_country            valid — 1 hop
order.customer                    invalid — ends on a reference slot
a.b.c.d.e                         invalid — exceeds four segments
```

The four-segment cap is a legibility limit as much as a technical one: a rule
nobody can read is a rule nobody maintains, and each hop is a join in whatever
eventually enforces it. The path editor (§13.5) stops offering reference slots at
the fourth segment, so the limit is felt as the picker running out of options
rather than as an error message.

This reuses the existing binding machinery: a binding already maps a parameter to
a slot, and now maps it to a path of slots. The static checker needs no new
concepts, only a path resolver.

### 9.3 Enforceability

Schema validators are **not expressible as CHECK constraints**. SQL CHECK may not
reference another table in any mainstream engine. A cross-entity rule can only be
enforced by a trigger, by a materialized denormalized column with a CHECK on it,
or by application code.

Designer records the rule regardless — capturing the intent has value even when
the database cannot hold it — but the tool must not imply the database will
enforce it. Hence the `enforcement` flag. `database` means "generate a trigger on
export"; `[V2]` since no export exists yet, v1 stores the flag, shows it in the
form, and the model check notes that nothing generates it.

A path that leaves the Schema makes this sharper: such a rule crosses a database
boundary as well as a table one, so `database` enforcement may be impossible
rather than merely unimplemented. The model check flags that combination.

---

## 10. Context

A namespace, arranged in a tree. Every Validator, Type, Property, Entity and
Schema belongs to exactly one Context. BaseTypes belong to none and are always
visible.

### 10.1 Visibility `[DECIDED]`

An item is visible from Context C if it belongs to C **or to any ancestor of C**.
Ordinary lexical scoping, which is what makes a shared root Context useful.

The "show only this Context" flag survives as a **filter on the browser lists**.
It does not change reference resolution — a flag that alters resolution can
silently invalidate a model when toggled.

- Sibling contexts are never visible to each other.
- Shadowing: the nearer name wins. The tool warns when a new item shadows an
  ancestor's name.
- Moving an item between Contexts is allowed only if every referencing item can
  still see it at the new location. Moving an Entity may also change its Schema
  membership (§9.1); the confirmation says so.

Note the interaction with §9.1 worth designing around: a shared Entity placed in
a **common ancestor** Context is visible to every Schema below it and belongs to
none of them, which is exactly the right home for a `Customer` that several
Schemas reference. Placing shared Entities high in the tree is the intended
idiom.

---

## 11. Referential integrity

References that exist: Type → parent Type, Type → Validator, Property → Type,
Entity → parent Entity, Entity → Property (via slot), Entity → Entity (via
reference slot), Entity → Validator, Schema → Validator, Schema → Entity (as
validator anchors and path segments), Validator → Validator, item → Context.

- **Delete is refused** while any item references the target; the tool lists the
  referencing items. This covers Entities that are extended, referenced, used as
  a Schema validator anchor, or traversed by a path. Schema *membership* alone
  never blocks a delete, since membership is derived rather than stored.

### 11.1 Recursive Context delete `[DECIDED]`

Deleting a Context deletes its whole subtree — child Contexts and all items
within them, including any Schema rooted there.

The confirmation dialog shows the **JSON subtree about to be removed**, plus a
count by kind, so the impact is visible in full rather than summarised.

The delete is **refused if anything outside the subtree references anything
inside it**, and the dialog lists those references instead. Internal references
disappear together. A Schema validator elsewhere whose path traverses an Entity
in the subtree counts as an outside reference.

### 11.2 Model check

On demand, and incrementally as items are edited:

- dangling references
- Type parent cycles, Entity extension cycles, Validator cycles
- unbound validator parameters
- **binding type errors and warnings** (§5.5)
- **nested schema roots** — error (§9.1)
- more than one Schema in a Context — error
- Schema validator whose anchor is not a member — error
- **unresolvable paths**, paths ending on a reference slot, paths exceeding four
  segments, paths reaching an Entity not visible from the Schema's Context —
  errors (§9.2)
- Schema validator with `enforcement = database` whose path leaves the Schema —
  warning, likely unenforceable at the database level (§9.3)
- duplicate names; shadowing warnings
- Entity validator bound to a reference slot — error (§7.2)
- reference slots targeting an abstract Entity — error
- reference slots whose target has no identity — error
- reference slots whose target has concrete descendants — warning (§8.2)
- abstract Entities with no concrete descendant — warning
- Schema validator with `enforcement = database` — note, nothing generates it yet
- slot overrides that widen rather than narrow — error
- `set_null` on a required slot — error
- concrete Entities belonging to no Schema, Schemas with fewer than two members,
  and orphaned items — informational

Entity *reference* cycles are legal and are not reported.

---

## 12. Persistence `[DECIDED]`

**v1: a single JSON document per model.** Diffs well in git, loads whole, no
dependency. YAML is an acceptable substitute if hand-editing matters more than
tooling.

Structure: a flat list per kind, every item keyed by UUID, every reference stored
as a UUID string. Do not nest — with extension and reference slots the model is a
graph, not a tree, and nesting forces an arbitrary spanning tree plus fixups on
load.

Non-native literals are stored per §4.1. Paths are stored as ordered lists of
slot UUIDs, not dotted strings, so a slot rename does not break a rule; the
dotted form is rendered for display only. **Schema membership is not stored at
all** — it is recomputed from the Context tree on load, which is what keeps it
from going stale.

The file carries a **schema version** from the first release.

The same flat-per-item JSON shape serves the editor's JSON tab (§13.6) and the
recursive-delete preview (§11.1).

`[V2]` A SQLAlchemy-backed store for the model catalogue itself. All model access
goes through a repository interface (`load`, `save`, `items_in_context`,
`references_to`) with the JSON implementation behind it. No domain class knows
how it is stored.

This concerns storing *Designer's own* model. Export of the authored model is
separate (§14).

Also required: dirty tracking with a save-on-exit prompt, and **undo/redo** via a
command stack where every mutation is an object with `do` and `undo`.

---

## 13. Application

### 13.1 Window `[DECIDED]`

- Menu bar, central area, status line.
- Opens maximised. No portable call exists: `state("zoomed")` on Windows,
  `attributes("-zoomed", True)` on X11, geometry from `winfo_screenwidth` /
  `winfo_screenheight` on macOS.
- **Minimum window size 1024 × 768**, enforced with `root.minsize(1024, 768)`,
  clamped to the screen if the display is somehow smaller — `minsize` larger than
  the screen leaves parts of the window unreachable.
- The editor pane has its own minimum height, so shrinking to 768 cannot squeeze
  the form to nothing.
- Window geometry, sash positions, collapse state and pins are saved and
  restored. Sash positions must be applied after the window is mapped
  (`after_idle`) or they are silently ignored.

### 13.2 Layout `[DECIDED]` — back to five columns

A vertical `ttk.PanedWindow` with two panes:

- **Upper** — a horizontal `ttk.PanedWindow` with five children, left to right:
  **Context, Entity, Property, Type, Validator**.
- **Lower** — the editor.

**There is no Schema column.** With membership derived from the Context subtree
and at most one Schema per Context, a Schema column would list the same
information the Context tree already shows. Instead:

- Schema roots are **badged in the Context tree** — an icon or bold label — so
  the partition is visible at a glance.
- Selecting a schema-root Context puts a **Schema tab** in the editor beside the
  Context form, where cross-entity validators are edited.
- A **Make this Context a schema root** action creates the Schema item; it is
  disabled when an ancestor or descendant is already one, which is where the
  §9.1 nesting rule is felt.

The Schema remains a distinct item with its own UUID, name and validators. Only
its browsing surface merged into the Context column.

`ttk.Treeview` throughout: hierarchical for Context, Type and Entity, flat for
Property and Validator. One code path, sortable headings for free.

The **Entity column is an extension tree**, with abstract Entities shown in a
distinct style — italic, or a separate icon — since they never materialize.

Each column has a filter entry above its list.

### 13.3 Collapsible columns `[DECIDED]`

Auto-collapse and manual control coexist through **pinning**, so the two never
fight:

- A slim toolbar above the upper pane holds five toggle buttons, one per column.
- Every column has a **minimum usable width of 10 'm'**, measured at runtime with
  `tkinter.font.Font.measure("m") * 10` on the actual UI font rather than
  hardcoded in pixels, so the rule follows font size and DPI scaling.
- On resize, the visible columns' minimums are summed; if they exceed the
  available width, columns are auto-collapsed in a fixed priority order —
  Context, Validator, Type, Property, Entity — until they fit. On widening,
  auto-collapsed columns are restored in reverse order.
- **Toggling a column manually pins it.** A pinned column is never auto-collapsed
  and never auto-restored. A **Reset layout** command clears all pins.
- Collapsing calls `PanedWindow.forget(pane)`; restoring calls `insert(index,
  pane)` at the remembered position. `ttk.PanedWindow` has no real collapse, and
  driving a sash to zero leaves a dead draggable strip that fights the next
  resize — forget/insert is the reliable route.
- Each pane's last width is remembered, so restoring puts the layout back rather
  than redistributing evenly.
- Resize handling is debounced through `after`, since X11 delivers a stream of
  `<Configure>` events during a drag.

Note how the two numbers interact: at a default UI font, ten 'm' is roughly
100–110px, so five columns need around 550px and **all five fit inside the 1024px
minimum window** with room to spare. Auto-collapse is therefore not a normal-use
feature — it is a font-scaling safety net, firing when a high-DPI display or a
large accessibility font pushes 10 'm' past ~200px. That is the right role for
it, but the behaviour will rarely be exercised in ordinary testing and needs
deliberate testing at a large font size.

`[OPEN]` Ten 'm' is tight for a Treeview carrying an entity name, an icon and a
filter entry above it. Worth measuring once the columns are real; dropping to
five columns bought headroom, so raising the minimum is now cheap.

**The Context column is the intended default collapse**, which works only because
of the breadcrumb below.

### 13.4 Context breadcrumb `[DECIDED]`

A breadcrumb path sits at the top of the editor pane, above the form, showing the
active Context: `root › billing › invoicing`.

It exists because the Context selection filters every other column (§13.7) and
determines where a new item is created. With the Context column collapsed, the
breadcrumb is the only indicator of both — and now also the only indicator of
which Schema the active Context sits under, so a schema root in the path carries
the same badge it has in the tree.

- Each segment is clickable and switches the active Context to that ancestor.
- The final segment carries a dropdown listing child Contexts and siblings, so
  the tree can be navigated without restoring the column.
- The breadcrumb is always visible, whether or not the Context column is.

### 13.5 Path editor

Schema validator bindings need a path picker, not a text field. A cascading
selector rooted at the anchor offers, at each step, only that Entity's slots:
reference slots continue the path, value slots end it, and reference slots stop
being offered once four segments are reached (§9.2). Targets outside the Schema
are offered normally but marked, since crossing the boundary is legal and worth
seeing.

This makes an invalid path unconstructible rather than merely reported, which
matters because the dotted syntax is the one place a user could otherwise type
something the model check has to reject.

### 13.6 Editor pane `[DECIDED]` — generated form, plus a JSON tab

Below the breadcrumb, a notebook. Two tabs for most kinds, three for a
schema-root Context.

**Form tab.** Generated per kind. Common controls: `name`, `description`, and
read-only `uuid`, `created`, `modified`.

| Kind | Kind-specific editor |
|---|---|
| Context | parent selector; schema-root badge and the Make/Remove schema root action |
| Schema (tab on a schema-root Context) | derived member list, read-only; cross-entity validator list with anchor picker, path editor and `enforcement` flag |
| Entity | `abstract` checkbox; `extends` picker; slot table; validator list; identity; indexes; default order |
| Property | Type picker |
| Type | parent picker; validator list with argument bindings |
| Validator | leaf/composite switch; parameter list; expression `Text`; message |

The Schema tab's member list is **read-only by construction** — there is nothing
to edit, since membership follows the Context tree. Entities are added to a
Schema by moving them into its subtree, which the list should say plainly rather
than leaving the user hunting for an Add button.

Only the expression field is free text. `Text` with `undo=True` and tag-based
highlighting; tkinter has no code editor widget.

Validator binding rows — in the Type, Entity and Schema forms alike — show the
inferred BaseType next to each bound argument and flag §5.5 errors inline as the
binding is made.

The **slot table** is the most complex control in the application and the main
build risk. It shows inherited slots read-only above the Entity's own, so the
effective record is visible in one place, and offers an override action on an
inherited row that creates a narrowing slot (§8.1) rather than a duplicate. The
Type picker in that override is filtered to Types that narrow the inherited one.

**JSON tab.** Read-only in v1, showing the selected item in the same shape used
on disk, with a copy button. `[V2]` Editable once the form editor settles.

### 13.7 Column linkage `[DECIDED]` — hybrid

- The Context selection **filters** all four other columns.
- Selecting a schema-root Context filters the Entity column to that Schema's
  members, which is the behaviour the removed Schema column would have provided.
- Selecting an Entity **highlights** its Properties rather than hiding the rest;
  selecting a Property highlights its Type; selecting a Type highlights its
  Validators.
- Selecting an Entity also highlights the Entities it references, in a distinct
  colour from the extension relationship already visible in the tree.
- A **follow selection** toggle switches highlighting to filtering throughout.

### 13.8 Actions

Each column carries a small toolbar: **New**, **Duplicate**, **Delete**, mirrored
on a right-click menu and the Edit menu. New and Duplicate act on the focused
column, Delete on the selected row. Delete is disabled when nothing is selected
rather than appearing and disappearing inside the editor.

The editor has explicit **Apply** and **Revert**. Changing selection with pending
edits prompts.

### 13.9 Status line

Selected item's kind and name, model dirty state, and the result of the last
model check. The Context path lives in the breadcrumb (§13.4).

---

## 14. Deferred `[V2]`

- **Test bench** — enter sample values, see which validators pass or fail and
  why. Static checking catches type errors but says nothing about whether a rule
  expresses what was meant. Worth pulling into v1 if anything else can be
  dropped.
- Trigger generation for `enforcement = database` Schema validators (§9.3).
- Per-chain joined-table inheritance for polymorphic references (§8.2).
- Scalar union types (§8.2).
- Collections (§8.4).
- Editable JSON tab (§13.6).
- SQLAlchemy-backed model store (§12).
- Export: DDL, SQLAlchemy declarative classes, or Pydantic models, one Schema at
  a time.
- Multi-model library import.

---

## 15. Remaining open questions

1. Should Schema stop being a separate item and become two fields on Context — a
   `schema_root` flag and a validator list? It is now edited through the Context,
   browsed through the Context, and derives its membership from the Context. The
   argument against is that a Context would then hold both visibility and rules,
   and the Schema would lose its own name and description. The argument for is
   one fewer kind, one fewer file section, and no way to express the illegal
   states the model check now has to catch. (§9.1, §13.2)
2. Whether a 10 'm' minimum column width is workable for a Treeview with a filter
   entry, or should be raised. A measurement, not a decision. (§13.3)
