# Designer — Standard Validator Library

29 August 2026. **Accepted in full.** An appendix to the main specification;
§5.7 of the spec records how the library attaches to the model.

Reconciled with *designer-signature-table.md*, which is authoritative for every
type rule referenced here.

---

## 1. Where built-ins live

**Global, read-only, like BaseTypes.** The library is not part of any model
document. It has no Context, is visible everywhere, and cannot be edited or
deleted.

The alternative — seeding a copy of the library into each new model's root
Context — was rejected. It would duplicate forty items into every file, freeze
each model against the library version it was created with, and let a user
silently break `non_empty` for one project and not another.

Three things make the global choice safe:

- **Stable UUIDs.** Each built-in's UUID is a UUIDv5 over a fixed Designer
  namespace and the validator's canonical name. Deterministic, identical on every
  installation, and structurally distinguishable from the v4 UUIDs of authored
  items. A model file referencing `max_length` refers to the same UUID everywhere.
- **A recorded library version.** The model file carries `library_version`
  alongside `schema_version` (§12). Opening a file that references a built-in this
  installation does not have produces a precise diagnostic — "requires standard
  library v3, this is v2" — rather than a dangling reference.
- **Fork to model.** A context-menu action on any built-in copies it into the
  active Context as an ordinary, editable Validator with a fresh v4 UUID.
  Existing bindings keep pointing at the built-in; the fork is a starting point,
  not a replacement. This is the escape hatch that makes read-only acceptable.

Built-ins never appear in the saved document. Only references to them do.

## 2. Delivered as a model fragment, not as code

The library ships as **a JSON document in the ordinary model file format**,
loaded at startup into a read-only registry.

This is worth doing for a reason beyond tidiness: it makes the library the first
real exercise of the file format, and it doubles as the worked example that
pre-build gap 3 asks for. If the format cannot express forty validators
comfortably, that is something to discover before the UI exists, not after.

It also means no second code path. A built-in is a Validator; the registry is a
second source of Validators for name resolution and UUID lookup, and nothing else
in the domain model needs to know the difference.

## 3. Three things the library forces into the specification `[DECIDED]`

Writing the library out surfaced three gaps in the expression language. All three
are now settled, and the full consequences are worked out in
*designer-signature-table.md*.

### 3.1 Free functions instead of methods

The sandbox whitelist (§5.4) bans attribute access outright, which is the right
rule because it is absolute and needs no case analysis. But it makes `value.strip()`
and `value.startswith(p)` unavailable, and half of string validation wants them.

**Solution: provide the string operations as free functions in the evaluation
namespace**, so the ban on attribute access stays total:

| Function | Signature |
|---|---|
| `len(s)` | string → integer |
| `lower(s)`, `upper(s)`, `strip(s)` | string → string |
| `starts_with(s, p)`, `ends_with(s, p)`, `contains(s, p)` | string, string → boolean |
| `regex_full_match(s, pattern)` | string, string → boolean |
| `is_finite(x)` | real → boolean |
| `precision(x)`, `scale(x)` | decimal → integer |
| `now()` | → datetime |
| `today()` | → date |
| `current()` | → datetime or date, by context (§4.4) |
| `seconds(n)`, `minutes(n)`, `hours(n)`, `days(n)`, `weeks(n)` | numeric → duration |
| `total_seconds(d)`, `total_days(d)` | duration → real |

Existing whitelist entries `abs`, `min`, `max`, `round`, `int`, `float` and `str`
stay. `Decimal` becomes lowercase **`decimal`**, matching every other type name,
and `decimal(real)` is rejected because it would capture binary rounding noise.
The `datetime` callable is dropped — temporal literals cover every case.

Note there is **no name collision** between these functions and the validators
that use them. A bare identifier in a *leaf* expression is a parameter or a
whitelisted function; a bare identifier in a *composite* expression is another
Validator. The two namespaces never meet, so a validator named `matches` calling
`regex_full_match` is unambiguous — though the library still avoids reusing a
function's name for a validator, because a human reader has no such guarantee.

### 3.2 List-valued arguments

`one_of` is the natural way to express an enumeration, and it needs
`value in options` where `options` is a list. Bindings currently supply "a
literal", meaning a scalar.

**Solution: allow a binding argument to be a list literal** of a single BaseType,
and add `in` / `not in` to the operator table with the signature
`T, list[T] → boolean`. The form editor renders a list argument as an editable
list of values rather than a text field.

This is the feature that makes enums expressible without a first-class enum
concept, which earlier revisions assumed was already possible (§8.2). It was not.

### 3.3 Determinism

`in_past` needs `now()`, and `now()` is not deterministic. §5.4 requires
expressions to be side-effect free, deterministic and terminating.

Rather than exclude temporal-relative rules, which are genuinely useful:

- **Determinism is derived, not declared.** A Validator is non-deterministic if
  its expression calls `now()` or `today()`, or if any composite operand is. The
  checker computes this; nothing is stored.
- **A binding to a non-deterministic Validator forces `enforcement = application`**
  and is excluded from CHECK-constraint generation on export.
- The Validator form marks non-deterministic built-ins, and the binding editor
  explains why the enforcement flag is locked.

This maps onto a real database rule rather than an invented one: PostgreSQL
rejects non-immutable functions inside CHECK constraints, so a rule using `now()`
could never have been a constraint anyway. Deriving the flag makes the tool say
so at authoring time.

### 3.4 Smaller additions to the operator table `[CLOSED]`

Also missing, and needed by the library: `%`, `not` on booleans, and the `in` /
`not in` forms above. All are now specified in *designer-signature-table.md*,
along with a fourth the library did not surface — **duration constructors**,
without which `duration` had no literal form and `(end - start) < days(30)` could
not be written at all.

Note that `%` is defined for `integer` and `decimal` only, so `multiple_of`
(§4.3) does not apply to `real`. That is the right restriction: a remainder test
against binary floating point is not a question with a reliable answer.

---

## 4. The catalogue

Forty validators. Every one is parameterless or takes named parameters; `value`
is the implicit argument. Messages interpolate parameters.

### 4.1 Comparison — any ordered BaseType

Usable on `integer`, `real`, `decimal`, `string`, `date`, `time`, `datetime`.
The binding's static type check (§5.6) rejects nonsense combinations, so one
validator serves all of them.

| Name | Parameters | Expression | Message |
|---|---|---|---|
| `equals` | `other` | `value == other` | must equal {other} |
| `not_equals` | `other` | `value != other` | must not equal {other} |
| `min_value` | `min` | `value >= min` | must be at least {min} |
| `max_value` | `max` | `value <= max` | must be at most {max} |
| `greater_than` | `min` | `value > min` | must be greater than {min} |
| `less_than` | `max` | `value < max` | must be less than {max} |
| `between` | `min`, `max` | `min <= value <= max` | must be between {min} and {max} |
| `one_of` | `options` | `value in options` | must be one of {options} |
| `not_one_of` | `options` | `value not in options` | must not be one of {options} |

`one_of` is how an enumeration is modelled: a Type over `string` with
`one_of(["draft", "sent", "paid"])`.

### 4.2 String

| Name | Parameters | Expression | Message |
|---|---|---|---|
| `non_empty` | — | `len(value) > 0` | must not be empty |
| `min_length` | `min` | `len(value) >= min` | must be at least {min} characters |
| `max_length` | `max` | `len(value) <= max` | must be at most {max} characters |
| `exact_length` | `n` | `len(value) == n` | must be exactly {n} characters |
| `length_between` | `min`, `max` | `min <= len(value) <= max` | must be {min}–{max} characters |
| `matches` | `pattern` | `regex_full_match(value, pattern)` | must match {pattern} |
| `starts_with` | `prefix` | `starts_with(value, prefix)` | must start with {prefix} |
| `ends_with` | `suffix` | `ends_with(value, suffix)` | must end with {suffix} |
| `contains` | `substring` | `contains(value, substring)` | must contain {substring} |
| `trimmed` | — | `value == strip(value)` | must not have leading or trailing whitespace |
| `is_lowercase` | — | `value == lower(value)` | must be lowercase |
| `is_uppercase` | — | `value == upper(value)` | must be uppercase |
| `is_identifier` | — | `regex_full_match(value, "[A-Za-z_][A-Za-z0-9_]*")` | must be a valid identifier |
| `is_email` | — | `regex_full_match(value, …)` | must be an email address |
| `is_url` | — | `regex_full_match(value, …)` | must be a URL |
| `is_uuid` | — | `regex_full_match(value, …)` | must be a UUID |
| `is_country_code` | — | `regex_full_match(value, "[A-Z]{2}")` | must be an ISO 3166-1 alpha-2 code |
| `is_currency_code` | — | `regex_full_match(value, "[A-Z]{3}")` | must be an ISO 4217 code |
| `no_control_characters` | — | `regex_full_match(value, "[^\\x00-\\x1f\\x7f]*")` | must not contain control characters |

`is_country_code` and `is_currency_code` check *shape*, not membership in the
real list. Checking membership would mean shipping and maintaining the lists, and
they change. The description says so, so nobody assumes otherwise.

### 4.3 Numeric

| Name | Parameters | Expression | Message |
|---|---|---|---|
| `positive` | — | `value > 0` | must be positive |
| `non_negative` | — | `value >= 0` | must not be negative |
| `negative` | — | `value < 0` | must be negative |
| `non_positive` | — | `value <= 0` | must not be positive |
| `multiple_of` | `n` | `value % n == 0` | must be a multiple of {n} |
| `is_finite` | — | `is_finite(value)` | must be a finite number |
| `max_precision` | `p` | `precision(value) <= p` | must have at most {p} significant digits |
| `max_scale` | `s` | `scale(value) <= s` | must have at most {s} decimal places |

`max_precision` and `max_scale` are the two the exporter recognises by UUID, to
emit `NUMERIC(p, s)` (§4). They are recognised by identity, not by parsing the
expression, so a forked copy will not be recognised — worth stating in their
descriptions.

`is_finite` matters more than it looks: `real` can hold NaN and infinity, JSON
cannot represent them portably, and databases reject them. A `real` Type destined
for storage usually wants it.

### 4.4 Temporal

| Name | Parameters | Expression | Deterministic |
|---|---|---|---|
| `in_past` | — | `value < current()` | no |
| `in_future` | — | `value > current()` | no |
| `not_in_past` | — | `value >= current()` | no |
| `not_in_future` | — | `value <= current()` | no |

All four are non-deterministic per §3.3 and are therefore application-enforced.
Absolute bounds — "no earlier than 2000-01-01" — use `min_value` from §4.1 and
stay deterministic.

`[DECIDED]` These four are **polymorphic over `date` and `datetime`**, and
`current()` is what makes that cost nothing. It is a constrained polymorphic
function returning `datetime` or `date`, so unification gives it the type of
`value`: bound to a `datetime` it means `now()`, bound to a `date` it means
`today()`. Binding one to a `time` fails the constraint, since "in the past" is
undefined for a wall-clock time with no date, and binding to an unresolved type
stays silent.

Splitting them into `in_past` and `date_in_past` was the alternative. It would
have kept every expression monomorphic at the cost of doubling the temporal
section and making the user pick the right one — and since unification was
already needed for `between` (§4.1), the polymorphic form needs no machinery that
does not already exist.

### 4.5 Boolean

| Name | Expression |
|---|---|
| `is_true` | `value` |
| `is_false` | `not value` |

Trivial, but a `boolean` slot that must be true is a real constraint, and without
these there is no way to say it.

### 4.6 Composites

Two, shipped mainly to exercise the composite mechanism against real content
rather than because the library needs many:

| Name | Expression |
|---|---|
| `non_blank` | `non_empty AND trimmed` |
| `is_safe_identifier` | `is_identifier AND max_length` |

`is_safe_identifier` inherits `max_length`'s `max` parameter, which demonstrates
the union-of-operand-parameters rule (§5.1) doing something useful.

---

## 5. Regular expressions

Six built-ins call `regex_full_match`, and `matches` takes a user-supplied
pattern. Two consequences:

- **Full match, not search.** `regex_full_match` anchors both ends. A partial
  match is the more common source of a validator that silently passes everything,
  and anyone wanting a search can write `.*…​.*`.
- **The pattern must be a literal**, or a parameter bound to one. That is what
  lets a malformed regex be an authoring-time error carrying the compile message,
  rather than a failure discovered in the test bench, and it lets compiled
  patterns cache by pattern string. Nothing needs a computed pattern.
- **Catastrophic backtracking is possible** with a user-supplied pattern, and
  Python's `re` has no timeout. In an authoring tool the blast radius is a hung
  UI during the test bench rather than a server outage, so this is a `[V2]`
  concern — but the test bench should run evaluation off the UI thread when it
  arrives, which is the natural place to add a guard.

---

## 6. Per-binding message override `[DECIDED]`

The message lives on the Validator, so every use of `max_length` would produce
the same wording. "must be at most 5 characters" is fine for a postcode and poor
for a product code that has a documented format.

**A binding carries an optional `message`**, overriding the Validator's when
present (spec §5.6). Half a field on an existing structure, and it removes the
main reason a user would fork a built-in — which is worth something, since a
forked `max_length` also loses exporter recognition (§4.3).

## 7. Versioning and additions

- `library_version` is an integer, incremented whenever a built-in is added,
  removed, or changes meaning. A message reword does not bump it.
- **Built-ins are never removed** once shipped, only deprecated: still resolvable,
  still functional, marked in the UI, excluded from pickers.
- A model file records the `library_version` it was authored against. A file from
  a newer library opens, and any unresolvable built-in becomes a named error
  rather than a mystery.

## 8. In the interface

- Built-ins appear in the **Validator column** in a distinct style, as abstract
  Entities do, and are visible from every Context.
- The column filter carries a **show built-ins** toggle, defaulting to off once a
  model has validators of its own. Forty built-ins swamping a user's five would
  make the column useless.
- Selecting one shows a read-only form, plus **Fork to model** (§1).
- Non-deterministic built-ins are marked, with the reason (§3.3).

## 9. Testing

Every built-in ships with **example values, passing and failing**, in the library
document alongside its definition. Two payoffs: pytest asserts the whole library
in one parameterised test from day one, and the test bench (deferred, §15 of the
spec) gets its fixtures for free when it arrives.

This is also the cheapest way to catch the class of bug this library is most
prone to — a regex that is subtly wrong in a way no reviewer notices.

---

## 10. Decisions taken

All seven accepted, 29 August 2026:

| | Decision | Where it now lives |
|---|---|---|
| 1 | Global read-only library, stable UUIDv5 identifiers, **Fork to model** | §1; spec §5.7 |
| 2 | Shipped as a JSON model fragment, doubling as the worked example | §2; spec §5.7, §14.1 |
| 3 | Whitelist extended with free functions rather than allowing methods | §3.1; spec §5.4; appendix §7 |
| 4 | List-valued binding arguments, with `in` / `not in` | §3.2; spec §5.6; appendix §6.8 |
| 5 | Determinism derived, forcing `enforcement = application` | §3.3; spec §5.7; appendix §8 |
| 6 | Optional per-binding message override | §6; spec §5.6 |
| 7 | `in_past` polymorphic over `date` and `datetime`, via `current()` | §4.4; appendix §7.4 |

Nothing in this document is open. The remaining pre-build item is the diagnostic
object (spec §16), which this library exercises through its own findings but does
not itself define.
