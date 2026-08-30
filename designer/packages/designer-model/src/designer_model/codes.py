"""The code registry.

Pure data. Every human-facing string lives here rather than at the site that
raises a finding, so wording is consistent, changing it is one edit, and tests
assert codes rather than sentences.

`blocks_export` is where the export gate lives declaratively. It is also why
severity can stay fixed per code: "Schema not closed" is a warning at all times
and still stops an export, because its definition says so rather than because
its severity changes with context.

Codes are permanent. A retired code is marked retired; its number is never
reused, because a code meaning one thing in v1 and another in v3 turns every
saved report and every test assertion into a trap.

    MOD1xx  references and incompleteness
    MOD2xx  cycles
    MOD3xx  naming
    MOD4xx  entities and slots
    MOD5xx  schemas
    MOD6xx  enforcement, export and orphans
    LIB1xx  the standard library
    EXP1xx-5xx  the expression checker (phase 2, see the signature table)
"""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Scope, Severity


@dataclass(frozen=True, slots=True)
class CodeDefinition:
    code: str
    severity: Severity
    scope: Scope
    title: str
    template: str
    blocks_export: bool = False
    retired: bool = False


def _d(code, severity, scope, title, template, blocks_export=False):
    return CodeDefinition(code, severity, scope, title, template, blocks_export)


_ALL = [
    # --- MOD1xx  references and incompleteness ------------------------------
    _d(
        "MOD101", Severity.INCOMPLETE, Scope.ITEM, "No parent type", "Type {item} has no parent yet", blocks_export=True
    ),
    _d("MOD102", Severity.INCOMPLETE, Scope.ITEM, "No type", "Property {item} has no type yet", blocks_export=True),
    _d(
        "MOD103",
        Severity.INCOMPLETE,
        Scope.ITEM,
        "Slot has no property",
        "slot {slot} has no property yet",
        blocks_export=True,
    ),
    _d(
        "MOD104",
        Severity.INCOMPLETE,
        Scope.ITEM,
        "Slot has no target",
        "slot {slot} has no target entity yet",
        blocks_export=True,
    ),
    _d(
        "MOD105",
        Severity.INCOMPLETE,
        Scope.ITEM,
        "Rule has no anchor",
        "a rule in {item} has no anchor entity yet",
        blocks_export=True,
    ),
    _d("MOD106", Severity.INCOMPLETE, Scope.ITEM, "Unnamed", "this {kind} has no name yet", blocks_export=True),
    _d(
        "MOD107",
        Severity.INCOMPLETE,
        Scope.ITEM,
        "Binding has no validator",
        "a binding in {item} names no validator",
        blocks_export=True,
    ),
    _d(
        "MOD111",
        Severity.ERROR,
        Scope.ITEM,
        "Dangling reference",
        "{field} points at {target}, which does not exist",
        blocks_export=True,
    ),
    _d(
        "MOD112",
        Severity.ERROR,
        Scope.ITEM,
        "Chain reaches no base type",
        "the parent chain of {item} never reaches a base type",
        blocks_export=True,
    ),
    _d(
        "MOD113",
        Severity.ERROR,
        Scope.ITEM,
        "Operand does not exist",
        "the expression of {item} names {target}, which does not exist",
        blocks_export=True,
    ),
    # --- MOD2xx  cycles -----------------------------------------------------
    _d(
        "MOD201",
        Severity.ERROR,
        Scope.MODEL,
        "Type parent cycle",
        "Type {item} is its own ancestor",
        blocks_export=True,
    ),
    _d(
        "MOD202",
        Severity.ERROR,
        Scope.MODEL,
        "Extension cycle",
        "Entity {item} extends itself, directly or through others",
        blocks_export=True,
    ),
    _d(
        "MOD203",
        Severity.ERROR,
        Scope.MODEL,
        "Validator cycle",
        "Validator {item} refers to itself, directly or through others",
        blocks_export=True,
    ),
    _d(
        "MOD204", Severity.ERROR, Scope.MODEL, "Context cycle", "Context {item} is its own ancestor", blocks_export=True
    ),
    # --- MOD3xx  naming -----------------------------------------------------
    _d(
        "MOD301",
        Severity.ERROR,
        Scope.CONTEXT,
        "Duplicate name",
        "{other} already uses the name {name} in this context",
        blocks_export=True,
    ),
    _d(
        "MOD302",
        Severity.WARNING,
        Scope.CONTEXT,
        "Shadows an ancestor",
        "{name} hides {other}, defined further up the context tree",
    ),
    _d(
        "MOD303",
        Severity.ERROR,
        Scope.ITEM,
        "Name is not an identifier",
        "{name} is not a valid identifier",
        blocks_export=True,
    ),
    _d(
        # item scope, not model: it compares a name against the standard
        # library, which does not change, so it can be reported the moment the
        # name is set rather than waiting for a full check
        "MOD304",
        Severity.INFO,
        Scope.ITEM,
        "Shadows a built-in",
        "{name} takes precedence over the built-in of that name in this context",
    ),
    # --- MOD4xx  entities and slots -----------------------------------------
    _d(
        "MOD401",
        Severity.ERROR,
        Scope.ITEM,
        "Reference to an abstract entity",
        "slot {slot} points at {target}, which is abstract and has no table",
        blocks_export=True,
    ),
    _d(
        "MOD402",
        Severity.ERROR,
        Scope.ITEM,
        "Target not visible",
        "slot {slot} points at {target}, which is not visible from this context",
        blocks_export=True,
    ),
    _d(
        "MOD403",
        Severity.ERROR,
        Scope.ITEM,
        "Target has no identity",
        "slot {slot} points at {target}, which has no identity to reference",
        blocks_export=True,
    ),
    _d(
        "MOD404",
        Severity.WARNING,
        Scope.MODEL,
        "Target has descendants",
        "slot {slot} reaches only {target}'s own rows, not its descendants'",
    ),
    _d(
        "MOD405",
        Severity.WARNING,
        Scope.MODEL,
        "Abstract entity materialises nothing",
        "{item} is abstract and nothing concrete extends it",
    ),
    _d(
        "MOD406",
        Severity.INCOMPLETE,
        Scope.ITEM,
        "No identity",
        "concrete Entity {item} has no identity yet",
        blocks_export=True,
    ),
    _d(
        "MOD407",
        Severity.ERROR,
        Scope.ITEM,
        "Override changes slot kind",
        "slot {slot} changes the kind of the slot it overrides",
        blocks_export=True,
    ),
    _d(
        "MOD408",
        Severity.ERROR,
        Scope.ITEM,
        "Override has nothing to override",
        "slot {slot} declares an override but no inherited slot of that name exists",
        blocks_export=True,
    ),
    _d(
        "MOD409",
        Severity.ERROR,
        Scope.ITEM,
        "Identity redeclared",
        "{item} declares an identity, but {other} already declares one above it",
        blocks_export=True,
    ),
    _d(
        "MOD410",
        Severity.ERROR,
        Scope.ITEM,
        "Unknown slot referenced",
        "{field} names slot {slot}, which is not one of this entity's slots",
        blocks_export=True,
    ),
    _d(
        "MOD411",
        Severity.ERROR,
        Scope.ITEM,
        "set_null on a required slot",
        "slot {slot} is required, so on_delete cannot set it null",
        blocks_export=True,
    ),
    _d(
        "MOD412",
        Severity.ERROR,
        Scope.ITEM,
        "Override widens optionality",
        "slot {slot} makes an inherited required slot optional",
        blocks_export=True,
    ),
    _d(
        "MOD413",
        Severity.ERROR,
        Scope.ITEM,
        "Override widens the type",
        "slot {slot} widens the inherited type rather than narrowing it",
        blocks_export=True,
    ),
    _d(
        "MOD414",
        Severity.ERROR,
        Scope.ITEM,
        "Rule bound to a reference slot",
        "a rule in {item} binds {slot}, a reference slot with no value to test",
        blocks_export=True,
    ),
    # --- MOD5xx  schemas ----------------------------------------------------
    _d(
        "MOD501",
        Severity.ERROR,
        Scope.ITEM,
        "Abstract member",
        "{target} is abstract and cannot be a member of {item}",
        blocks_export=True,
    ),
    _d(
        "MOD502",
        Severity.ERROR,
        Scope.ITEM,
        "Member not visible",
        "{target} is not visible from {item}'s context",
        blocks_export=True,
    ),
    _d(
        "MOD503",
        Severity.WARNING,
        Scope.ITEM,
        "Schema not closed",
        "{source}.{slot} references {target}, which is not a member of {item}",
        blocks_export=True,
    ),
    _d(
        "MOD504",
        Severity.ERROR,
        Scope.ITEM,
        "Anchor is not a member",
        "a rule in {item} is anchored on {target}, which is not a member",
        blocks_export=True,
    ),
    _d(
        "MOD505",
        Severity.ERROR,
        Scope.ITEM,
        "Path too long",
        "the path for {param} has {length} segments; four is the limit",
        blocks_export=True,
    ),
    _d(
        "MOD506",
        Severity.ERROR,
        Scope.ITEM,
        "Path does not resolve",
        "the path for {param} does not resolve at segment {position}",
        blocks_export=True,
    ),
    _d(
        "MOD507",
        Severity.ERROR,
        Scope.ITEM,
        "Path ends on a reference",
        "the path for {param} ends on a reference slot, not a value",
        blocks_export=True,
    ),
    _d(
        "MOD508",
        Severity.ERROR,
        Scope.ITEM,
        "Path traverses a value slot",
        "the path for {param} passes through {slot}, which is not a reference",
        blocks_export=True,
    ),
    _d(
        "MOD509",
        Severity.ERROR,
        Scope.ITEM,
        "Path leaves the schema",
        "the path for {param} reaches {target}, which is not a member",
        blocks_export=True,
    ),
    _d(
        "MOD510",
        Severity.INFO,
        Scope.ITEM,
        "Nothing to relate",
        "{item} has fewer than two members, so nothing spans them",
    ),
    # --- MOD6xx  enforcement, export and orphans ----------------------------
    _d("MOD601", Severity.INFO, Scope.MODEL, "Referenced by nothing", "{item} is referenced by nothing"),
    _d(
        "MOD602",
        Severity.WARNING,
        Scope.ITEM,
        "No constraint can carry this",
        "{item} binds {validator}, which is not deterministic; no check constraint can enforce it",
    ),
    _d(
        "MOD603",
        Severity.INFO,
        Scope.ITEM,
        "Nothing generates this yet",
        "a rule in {item} asks for database enforcement, which nothing generates yet",
    ),
    _d("MOD604", Severity.INFO, Scope.MODEL, "In no schema", "{item} is concrete but belongs to no schema"),
    # --- LIB1xx  the standard library ---------------------------------------
    _d(
        "LIB101",
        Severity.ERROR,
        Scope.ITEM,
        "Unknown built-in",
        "{item} uses built-in {target}, which this standard library does not have",
        blocks_export=True,
    ),
    _d("LIB102", Severity.INFO, Scope.ITEM, "Deprecated built-in", "{item} uses {target}, which is deprecated"),
]

# --- EXPnnn  the expression checker -------------------------------------
# These carry `{message}` rather than a fixed sentence: the checker computes
# the detail (which two types, which argument, which function) and a static
# template cannot hold it. Severity, title, scope and the export gate still
# live here, which is what the registry is for.
_EXPRESSION = [
    ("EXP101", "Attribute access", Scope.ITEM),
    ("EXP102", "Construct not permitted", Scope.ITEM),
    ("EXP103", "Subscripting", Scope.ITEM),
    ("EXP104", "Lambda", Scope.ITEM),
    ("EXP105", "Comprehension", Scope.ITEM),
    ("EXP106", "Conditional expression", Scope.ITEM),
    ("EXP107", "Assignment", Scope.ITEM),
    ("EXP108", "Await", Scope.ITEM),
    ("EXP109", "f-string", Scope.ITEM),
    ("EXP110", "Argument unpacking", Scope.ITEM),
    ("EXP111", "Keyword argument", Scope.ITEM),
    ("EXP112", "Cannot parse", Scope.ITEM),
    ("EXP201", "Exactness would be lost", Scope.ITEM),
    ("EXP202", "No such operation", Scope.ITEM),
    ("EXP203", "Time has no arithmetic", Scope.ITEM),
    ("EXP204", "Date and datetime", Scope.ITEM),
    ("EXP205", "Units not named", Scope.ITEM),
    ("EXP206", "Not ordered", Scope.ITEM),
    ("EXP207", "No implicit truth value", Scope.ITEM),
    ("EXP208", "Substring membership", Scope.ITEM),
    ("EXP209", "Identity comparison", Scope.ITEM),
    ("EXP210", "Floor division", Scope.ITEM),
    ("EXP211", "Unsupported operator", Scope.ITEM),
    ("EXP301", "No matching signature", Scope.ITEM),
    ("EXP302", "Argument must be a literal", Scope.ITEM),
    ("EXP303", "Renamed or removed", Scope.ITEM),
    ("EXP304", "Outside the allowed types", Scope.ITEM),
    ("EXP401", "List is not homogeneous", Scope.ITEM),
    ("EXP402", "Argument type mismatch", Scope.ITEM),
    ("EXP403", "Not a parameter", Scope.ITEM),
    ("EXP501", "Not a boolean", Scope.ITEM),
]

_ALL += [_d(code, Severity.ERROR, scope, title, "{message}", blocks_export=True) for code, title, scope in _EXPRESSION]

# the one expression finding that is advice rather than an error
_ALL.append(_d("EXP404", Severity.WARNING, Scope.ITEM, "Parameter never used", "{message}"))


REGISTRY: dict[str, CodeDefinition] = {d.code: d for d in _ALL}

BLOCKS_EXPORT = frozenset(d.code for d in _ALL if d.blocks_export)


def definition(code: str) -> CodeDefinition:
    try:
        return REGISTRY[code]
    except KeyError:
        raise KeyError(f"no such diagnostic code: {code}") from None


def severity(code: str) -> Severity:
    return definition(code).severity


def blocks_export(code: str) -> bool:
    return code in BLOCKS_EXPORT
