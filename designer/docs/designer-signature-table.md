# Designer — Expression Signature Table

29 August 2026. **Accepted in full.** An appendix to the main specification,
authoritative for everything §5.4 and §5.6 summarise.

---

## 1. How it is represented

A single module, `designer_model/expressions/signatures.py`, containing **pure
data and no logic**: lists of signature records that the checker walks. Nothing
in it imports anything from the checker, so the table can be tested, printed and
diffed independently of the code that consumes it.

```python
Signature(
    name:           str,                  # "len", "regex_full_match"
    params:         tuple[TypeExpr, ...],
    result:         TypeExpr,
    deterministic:  bool = True,
    variadic:       bool = False,         # min, max take two or more
    literal_params: tuple[int, ...] = (), # positions that must be literals
    constraint:     frozenset[str] | None = None,  # what a Var may become
)
```

`[CHANGED]` Functions are `Signature` records (`signatures.FUNCTIONS`); the
operators are tables of pairs (`ARITHMETIC`, `COMPARISON_REJECTS` and the like)
rather than records with a `key`, and rejections are `Reject(code, message)`
values in those tables. There is no per-signature `note`: a rejection carries
its own message.

A `TypeExpr` is one of:

- a **scalar** — one of the eight BaseTypes, or `duration`;
- `ListOf(TypeExpr)`;
- `Var(name, constraint)` — a type variable restricted to a named set, for
  genuinely polymorphic signatures.

A key may have **several signatures**. Resolution tries every one, without
side effects. Exactly one match decides the call. Several can match only while
an argument is an open parameter, and then nothing is bound yet: if they agree
on a result (`float(x)` is `real` whatever `x` is) that is the call's type; if
each returns the type of that same open argument (`abs`, `round`) the call has
the argument's type, so a later comparison settles both; otherwise it is
`unknown` until the context says more. Where a pair is deliberately illegal, the table
carries an explicit **rejection record** with its own message, so the checker
distinguishes "no rule exists" from "there is a rule and it says no" — the second
is worth a much better diagnostic.

Enumerating the numeric pairs rather than abstracting a promotion lattice is
deliberate. There are nine of them, they fit on one screen, and an explicit row
is easier to test and to argue about than a rule that computes the same answer.

---

## 2. The type universe

| Type | Origin | May be a slot type? |
|---|---|---|
| `integer`, `real`, `decimal`, `boolean`, `string`, `datetime`, `date`, `time` | BaseTypes (§4) | yes |
| `duration` | only from temporal subtraction or a duration constructor (§7.5) | **no** |
| `list[T]` | list literals in bindings (§5.6) | no |
| `unknown` | see §3 | no |

Useful sets, referenced throughout:

```
numeric   = {integer, real, decimal}
ordered   = numeric ∪ {string, date, time, datetime, duration}
equatable = ordered ∪ {boolean}
temporal  = {date, time, datetime}
```

---

## 3. `unknown` absorbs

Every operation with an `unknown` operand yields `unknown` and reports nothing.

This is not a convenience, it is required by §3.1. A Type with no parent yet has
no BaseType, so `value` is `unknown`, and without absorption every binding on
that Type would erupt in type errors while the user is still filling the form.
Incomplete must stay quiet.

`unknown` does double duty as the **poison type**: after the checker reports a
failure at some node, that node's type becomes `unknown`, so one mistake produces
one diagnostic rather than a cascade up the tree.

The rule that keeps this honest: **`unknown` never satisfies a requirement, it
only suppresses a complaint.** A binding whose type resolves to `unknown` is
reported as `incomplete`, never as valid.

---

## 4. Literals

**Numeric literals inside an expression are untyped** and take the type of the
context they appear in. `100` in `value <= 100` is an integer, a real or a
decimal depending on `value`.

Without this rule, `price <= 1.5` on a `decimal` price would be a real/decimal
error — the firewall firing on a literal the user wrote to be exact. Untyped
literals were introduced for exactly this reason in Go and it is the right answer
here too.

- An integer-shaped literal is compatible with `integer`, `real` and `decimal`.
- A fraction-shaped literal is compatible with `real` and `decimal`, **not**
  `integer`.
- When nothing constrains it — both operands are literals — an integer-shaped
  literal defaults to `integer` and a fraction-shaped one to `decimal`. Decimal,
  not real, because the source text is exact and reading `1.5` as binary floating
  point loses information the user wrote down.

String, boolean and temporal literals are typed as written.

**Binding arguments are different.** They are supplied through the form, not
written in the expression, and their required type is *inferred* (§5) and shown
in the binding row (§13.6 of the spec). The supplied literal is then checked
against that inferred type. The form can therefore offer the right editor — a
date picker, a checkbox, a list editor — instead of a text field.

---

## 5. Inferring parameter types

The checker runs two passes over a binding.

**Pass 1 — inference.** Seed `value` (or each bound slot or path) with its known
type, give every declared parameter a fresh type variable, walk the AST
generating constraints from the signature table, and solve by unification.

Unification is what makes `between` work. From `min <= value <= max` with
`value: date`, both comparisons force `min` and `max` to `date`, and the form
offers date pickers. No per-validator annotation is needed, which is the whole
point of §5.1's "Validators are not typed".

**Pass 2 — argument checking.** Each supplied literal is checked against its
inferred parameter type. A parameter that unification leaves unconstrained — it
appears nowhere in the expression — is the "parameter never used" warning
from §5.6.

Overload resolution during pass 1 is as §1 describes: every signature is tried
without side effects; one match decides; several match only while an argument is
an open parameter, and then the call gives the result they agree on, or the
open argument's type when each returns its own, or `unknown`. `[CHANGED]` There
is no deferral and retry pass: an open argument's type flows back to it through
the comparison the call stands in, which is the same answer in one walk.

An untyped literal stays open as long as it can (§4). In a list, `[1.5, 2.5]`
beside a `real` is a list of reals, and an open parameter in a list takes the
list's type; in `min`/`max`, literals alone stay open for the context to settle;
beside an open parameter (`x * 2`), the literal takes the parameter's type and
the comparison then settles both. `/` is the exception: two integers make a
real, so `x / 2` is not assumed to be `x`'s type.

---

## 6. Operators

### 6.1 Unary

| Operator | Operand | Result |
|---|---|---|
| `-` | `integer` | `integer` |
| `-` | `real` | `real` |
| `-` | `decimal` | `decimal` |
| `-` | `duration` | `duration` |
| `+` | any numeric, or `duration` | same type |
| `not` | `boolean` | `boolean` |

`not` on a non-boolean is a **rejection**, not a missing rule: "no implicit truth
value; compare explicitly". This is the rule that closes Python's truthiness hole
— `not value` on a string would otherwise silently mean "is empty".

### 6.2 Arithmetic on numerics — `+`, `-`, `*`

All nine pairs, exhaustively:

| left | right | result |
|---|---|---|
| `integer` | `integer` | `integer` |
| `integer` | `real` | `real` |
| `real` | `integer` | `real` |
| `real` | `real` | `real` |
| `integer` | `decimal` | `decimal` |
| `decimal` | `integer` | `decimal` |
| `decimal` | `decimal` | `decimal` |
| `real` | `decimal` | **rejected** |
| `decimal` | `real` | **rejected** |

Rejection message: *"`real` and `decimal` cannot be combined — binary floating
point would destroy the exactness of the decimal. Convert explicitly with
`float(…)` if that is what you intend."*

### 6.3 Division and remainder

| left | op | right | result |
|---|---|---|---|
| `integer` | `/` | `integer` | `real` |
| `integer` | `/` | `real` | `real` |
| `real` | `/` | `integer` or `real` | `real` |
| `integer` | `/` | `decimal` | `decimal` |
| `decimal` | `/` | `integer` or `decimal` | `decimal` |
| `real` / `decimal` mixed | `/` | | **rejected**, as §6.2 |
| `integer` | `%` | `integer` | `integer` |
| `decimal` | `%` | `decimal` | `decimal` |
| anything else | `%` | | no meaning (`EXP202`); `time` is rejected (`EXP203`) |

`integer / integer → real` follows Python, and it has a sharp edge worth naming:
`(a / b) < price` with a `decimal` price is a real/decimal rejection (`EXP201`),
because the division produced a real — when `a` and `b` are known integers.
The message then adds *"integer division produces a real; use % or compare
against a real"* (built 19 October). When `a` and `b` are parameters whose types
are still open the pair is not rejected at all: nothing forces them to integer. Floor division `//` is
not supported — one division operator is enough and the second invites confusion
about which one a rule meant.

### 6.4 Strings

| left | op | right | result |
|---|---|---|---|
| `string` | `+` | `string` | `string` |

Nothing else. `string * integer` is rejected (`EXP211`, *"strings cannot be
multiplied."*); there is no use for it in a predicate.

### 6.5 Temporal

| left | op | right | result |
|---|---|---|---|
| `datetime` | `-` | `datetime` | `duration` |
| `date` | `-` | `date` | `duration` |
| `datetime` | `+` or `-` | `duration` | `datetime` |
| `date` | `+` or `-` | `duration` | `date` |
| `duration` | `+` or `-` | `duration` | `duration` |
| `duration` | `*` | `integer` or `real` | `duration` |
| `integer` or `real` | `*` | `duration` | `duration` |
| `duration` | `/` | `integer` or `real` | `duration` |
| `duration` | `/` | `duration` | `real` |
| `date` | `-` | `datetime` | **rejected** — no common zone (§4.2) |
| `time` | any arithmetic | anything | **rejected** (§4.3) |
| `date` or `datetime` | `+`/`-` | `integer` | **rejected** — *"use `days(n)` to say what the number means"* |

That last rejection matters. `order_date + 30` reads naturally and is ambiguous
about units, so the table refuses it and names the fix.

### 6.6 Comparison — `<`, `<=`, `>`, `>=`

Both operands must be in `ordered` and resolve to the same type under the numeric
pairs of §6.2. Result is always `boolean`.

| case | outcome |
|---|---|
| same scalar type, in `ordered` | `boolean` |
| numeric pair legal per §6.2 | `boolean` |
| `real` with `decimal` | **rejected**, as §6.2 |
| `date` with `datetime` | **rejected** — *"a date has no time or zone; convert explicitly"* |
| `time` with `time` | `boolean` — the one operation `time` supports |
| `string` with `string` | `boolean`, lexicographic |
| `boolean` with anything | **rejected** — *"booleans are not ordered; use `==`"* |
| `duration` with `duration` | `boolean` |

**Chained comparisons are supported** — `min <= value <= max` is one `ast.Compare`
node with two comparators. Each adjacent pair is checked independently and the
result is `boolean`. This is the form half the standard library is written in, so
it is not optional.

### 6.7 Equality — `==`, `!=`

As §6.6, but the operand set is `equatable`, so `boolean == boolean` is legal.
`is` and `is not` are **not supported**: identity is meaningless for values here
and the distinction from `==` is a reliable source of bugs.

### 6.8 Membership — `in`, `not in`

| left | right | result |
|---|---|---|
| `T` (scalar) | `list[U]` where `T` and `U` unify per §6.6 | `boolean` |
| `string` | `string` | **rejected** — *"use `contains(haystack, needle)`"* |
| anything | anything else | rejected |

Rejecting substring `in` is deliberate. Python's `"a" in "abc"` and
`"a" in ["a"]` mean different things with identical syntax, and a validator that
silently switched behaviour when its argument changed shape would be very hard to
diagnose.

The list must be **homogeneous**; a mixed list is an error reported against the
argument, not the expression (§5.6).

### 6.9 Boolean connectives

| left | op | right | result |
|---|---|---|---|
| `boolean` | `and` | `boolean` | `boolean` |
| `boolean` | `or` | `boolean` | `boolean` |

Both operands must be typed `boolean`; there is no truthiness. Note these are the
*leaf* connectives, written lowercase as Python. The uppercase `AND` / `OR` /
`XOR` / `NOT` of §5.1 belong to the composite language, which has its own parser
and never reaches this table.

Conditional expressions (`A if C else B`), comprehensions, lambdas, walrus,
subscripts and slices are all **rejected by the whitelist** before typing, and
need no signatures.

---

## 7. Functions

### 7.1 String

| Signature | Result | Notes |
|---|---|---|
| `len(string)` | `integer` | |
| `lower(string)`, `upper(string)`, `strip(string)` | `string` | |
| `starts_with(string, string)` | `boolean` | |
| `ends_with(string, string)` | `boolean` | |
| `contains(string, string)` | `boolean` | haystack first |
| `regex_full_match(string, string)` | `boolean` | second argument must be a **literal or a parameter bound to a literal** |

The literal restriction on the pattern buys two things: the pattern compiles once
and caches, and a malformed regex becomes an **authoring-time error with the
compile message** rather than a runtime failure in the test bench. A pattern
computed from string concatenation would forfeit both, and nothing needs one.

### 7.2 Numeric

| Signature | Result |
|---|---|
| `abs(integer)` | `integer` |
| `abs(real)` | `real` |
| `abs(decimal)` | `decimal` |
| `abs(duration)` | `duration` |
| `min(T, T, …)`, `max(T, T, …)` where `T ∈ ordered` | `T` |
| `round(real)` | `integer` |
| `round(real, integer)` | `real` |
| `round(decimal, integer)` | `decimal` |
| `is_finite(real)` | `boolean` |
| `precision(decimal)` | `integer` |
| `scale(decimal)` | `integer` |

`min` and `max` are variadic over two or more arguments that unify to one type.

What the evaluator does with them (`expressions/evaluate.py`), where the table
says only the type: `round` rounds half to even, as Python does; `precision`
counts digits as `NUMERIC(p, s)` does — `1234.50` is 6, `0.005` is 3 — and
`scale` counts places after the point, trailing zeros included.

### 7.3 Conversion

| Signature | Result | Notes |
|---|---|---|
| `int(real)`, `int(decimal)`, `int(string)` | `integer` | truncates a number; a string must be a whole number |
| `float(integer)`, `float(decimal)`, `float(string)` | `real` | the explicit escape from the firewall |
| `str(T)` for any `T` | `string` | lists too |
| `decimal(string)`, `decimal(integer)` | `decimal` | `decimal(1.5)` is refused as no signature matching — a fraction literal is already a decimal, so write `1.5` |
| `decimal(real)` | **rejected** | `EXP301`, with the dedicated message *"converting binary floating point to decimal captures rounding noise; use a decimal literal or a string"* |

Two changes from §5.4's provisional list. `Decimal` is renamed **`decimal`**,
lowercase, to match every other type name in the language — the capitalised form
was leaking a Python implementation detail into a user-facing DSL. And the
`datetime` callable is **dropped**: temporal literals cover every case, and a
constructor taking seven integers is a worse way to write a date than writing the
date.

### 7.4 Temporal and polymorphic `current()`

| Signature | Result | Deterministic |
|---|---|---|
| `now()` | `datetime` | **no** |
| `today()` | `date` | **no** |
| `current()` | `T` where `T ∈ {datetime, date}` | **no** |

The clock is UTC: `today()` is the UTC date, and `current()` is `today()` for a
`date` value and `now()` for a `datetime`.

`current()` is how §5.7's polymorphic temporal rule is expressed, and it needs no
dispatch machinery beyond the unification already present. The library's
`in_past` is simply:

```
value < current()
```

Unification gives `current()` the type of `value`. Bound to a `datetime` it means
`now()`; bound to a `date` it means `today()`; bound to a `time` or anything else
the constraint fails and the checker reports `EXP304` *"this applies to date or
datetime, not time"*. Bound to `unknown` it stays `unknown` and says nothing.

### 7.5 Duration constructors and accessors

| Signature | Result |
|---|---|
| `seconds(N)`, `minutes(N)`, `hours(N)`, `days(N)`, `weeks(N)` where `N ∈ {integer, real, decimal}` | `duration` |
| `total_seconds(duration)`, `total_days(duration)` | `real` |

**These close a real hole.** The specification introduced `duration` as an
intermediate type from `datetime − datetime`, but provided no way to write one
down — so `(end - start) < 30` had no legal form, and `duration` was
unreachable in practice. The constructors give it a literal form, and they name
their units at the call site, which is why §6.5 can safely reject bare
`date + integer`.

`total_seconds` and `total_days` return `real` rather than `decimal` because a
duration is a measurement, not money, and no exactness claim is being made.

---

## 8. Determinism

An expression is non-deterministic when it calls any function whose signature
carries `deterministic = False` — `now`, `today`, `current` — and a composite is
non-deterministic when any operand is. The model check, the library and the
exporter find those calls on the syntax tree (`sandbox.reads_clock`), so a
string that happens to contain `"now()"` is text, not a call. (They used a text
scan until 19 October, which counted it.)

The flag propagates upward and is never stored. It is used at three places: the
locked `enforcement` on a Schema binding, the warning on a Type or Entity
binding, and the marker in the Validator form.

---

## 9. Diagnostics

Every rejection in this document carries a **stable code** and its own message.
Codes group by prefix so the model check can filter:

| Prefix | Meaning | Example |
|---|---|---|
| `EXP1xx` | parse and whitelist | `EXP101` attribute access not permitted |
| `EXP2xx` | operator typing | `EXP201` real/decimal mixed; `EXP204` date compared with datetime |
| `EXP3xx` | function typing | `EXP301` no signature matches; `EXP302` regex pattern is not a literal |
| `EXP4xx` | binding and arguments | `EXP401` list literal not homogeneous; `EXP402` argument type mismatch |
| `EXP5xx` | result and shape | `EXP501` expression does not produce a boolean |

The code, its severity, the source offset and the substituted message are what
the diagnostic object (pre-build gap 2) has to carry — so writing this table
first is what makes that object designable rather than guessed at.

---

## 10. Testing the table exhaustively

Three tests, all cheap, and the first is the one that makes "complete" mean
something:

1. **The full matrix, as a golden file.** For each binary operator, generate the
   cross-product of the nine types on both sides (the eight BaseTypes and
   `duration`) — 81 cells per operator, and no table for `in` — and
   record the result type or the rejection code. Commit the rendered matrix. Any
   change to the table then shows up as a reviewable diff, and any pair nobody
   thought about appears as an explicit "no rule" cell rather than hiding.
2. **Every signature is reachable.** Assert that each record in the table matches
   at least one expression drawn from the standard library or the test corpus.
   An unreachable signature is either dead or a symptom of a resolution bug.
3. **The standard library type-checks clean.** Every built-in, bound to each
   BaseType it claims to support, produces no diagnostics; bound to one it does
   not, produces the expected code. This is the test that catches a signature
   table and a library drifting apart.

---

## 11. Decisions taken

All eleven accepted, 29 August 2026. Nothing in this document is open.

1. `unknown` as an absorbing type, required by incomplete items (§3).
2. Untyped numeric literals in expressions; inferred types for parameters (§4).
3. Unification for parameter inference, which is what makes `between` work
   without annotations (§5).
4. Numeric pairs enumerated rather than derived from a promotion lattice (§6.2).
5. No implicit truthiness, no `is`, no substring `in`, no floor division (§6).
6. Regex patterns must be literals, so they compile at authoring time (§7.1).
7. `Decimal` renamed `decimal`; the `datetime` callable dropped (§7.3).
8. `current()` as a constrained polymorphic function, replacing dispatch (§7.4).
9. **Duration constructors added** — without them `duration` is unusable (§7.5).
10. Stable diagnostic codes, which give gap 2 its shape (§9).
11. The operator matrix committed as a golden file (§10).

---

## 12. Known gaps `[FOUND WHILE BUILDING]`

Found by the crosscheck of 17 October 2026. The first three were fixed on 19
October (turn 157), each pinned by a test in `test_expressions.py`:

1. ~~**The first matching overload won**, binding an open parameter as it went:
   in `abs(x) < value` with a `decimal` value, `x` was inferred `integer`.~~
   **Fixed** — see §1: overloads are tried without side effects, and an
   ambiguous call waits for its context.
2. ~~**An untyped literal did not unify with a type variable**: `min(value, 1)`
   on a `decimal` value was refused.~~ **Fixed** — a literal argument is judged
   after the others have given the variable its type.
3. ~~**`x in [1, 2]` with `x` a parameter was refused**.~~ **Fixed** — an open
   variable on the left of `in` takes the list's element type.
4. ~~The two missing messages in §6.3 and §7.3.~~ **Built** on 19 October.

The crosscheck of 20 October found more of the same kind as 1–3, all fixed
then and pinned in `test_expressions.py`: a fraction literal in a list was fixed
as `decimal` before its context was seen (`value in [1.5, 2.5]` on a real was
refused); an open parameter inside a list was a "mixed list"; unary `-` and `+`
refused an open parameter; `min(1, 2.5)` was refused; an open parameter beside a
literal (`x * 2`) and in `min(value, x)` was never typed. The evaluator, for its
part, now lets a fraction literal meet a real as a real (`float(value) + 0.5`),
where it used to fail with a decimal/float mix.
