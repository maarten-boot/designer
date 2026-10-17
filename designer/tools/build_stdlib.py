"""Emit the standard validator library as a model fragment.

The library ships as JSON in the ordinary model format (spec §5.7) rather than
as code: no second code path, and it exercises the file format for real.

Run from the repository root:
    python3 tools/build_stdlib.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/designer-model/src")
)

from designer_model.ids import builtin_id

OUT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "packages/designer-model/src/designer_model/data/stdlib.json"
)
DEPRECATIONS_OUT = OUT.with_name("deprecations.json")
EXAMPLES_OUT = OUT.with_name("examples.json")

LIBRARY_VERSION = 1
STAMP = "2026-08-29T00:00:00Z"

# Deprecating a built-in (spec §5.7): never delete its entry below. Add it here
# as (name, replacement name or None, reason), and bump LIBRARY_VERSION; the
# version it is deprecated since is the one this run writes.
DEPRECATED: list[tuple[str, str | None, str]] = []

# name, parameters, expression, message, description
LEAVES: list[tuple[str, list[str], str, str, str]] = [
    # comparison — any ordered base type
    (
        "equals",
        ["other"],
        "value == other",
        "must equal {other}",
        "Equality against a fixed value.",
    ),
    (
        "not_equals",
        ["other"],
        "value != other",
        "must not equal {other}",
        "Inequality against a fixed value.",
    ),
    (
        "min_value",
        ["min"],
        "value >= min",
        "must be at least {min}",
        "An inclusive lower bound.",
    ),
    (
        "max_value",
        ["max"],
        "value <= max",
        "must be at most {max}",
        "An inclusive upper bound.",
    ),
    (
        "greater_than",
        ["min"],
        "value > min",
        "must be greater than {min}",
        "An exclusive lower bound.",
    ),
    (
        "less_than",
        ["max"],
        "value < max",
        "must be less than {max}",
        "An exclusive upper bound.",
    ),
    (
        "between",
        ["min", "max"],
        "min <= value <= max",
        "must be between {min} and {max}",
        "An inclusive range. Serves numbers and dates alike.",
    ),
    (
        "one_of",
        ["options"],
        "value in options",
        "must be one of {options}",
        "An enumeration, expressed as a list literal.",
    ),
    (
        "not_one_of",
        ["options"],
        "value not in options",
        "must not be one of {options}",
        "Excludes a fixed set of values.",
    ),
    # string
    ("non_empty", [], "len(value) > 0", "must not be empty", "At least one character."),
    (
        "min_length",
        ["min"],
        "len(value) >= min",
        "must be at least {min} characters",
        "A lower length bound.",
    ),
    (
        "max_length",
        ["max"],
        "len(value) <= max",
        "must be at most {max} characters",
        (
            "An upper length bound. Recognised by the exporter by identity to emit a "
            "length hint; a forked copy is not recognised."
        ),
    ),
    (
        "exact_length",
        ["n"],
        "len(value) == n",
        "must be exactly {n} characters",
        "A fixed length.",
    ),
    (
        "length_between",
        ["min", "max"],
        "min <= len(value) <= max",
        "must be {min}-{max} characters",
        "A length range.",
    ),
    (
        "matches",
        ["pattern"],
        "regex_full_match(value, pattern)",
        "must match {pattern}",
        "A regular expression, matched in full. The pattern must be a literal.",
    ),
    (
        "starts_with",
        ["prefix"],
        "starts_with(value, prefix)",
        "must start with {prefix}",
        "A required prefix.",
    ),
    (
        "ends_with",
        ["suffix"],
        "ends_with(value, suffix)",
        "must end with {suffix}",
        "A required suffix.",
    ),
    (
        "contains",
        ["substring"],
        "contains(value, substring)",
        "must contain {substring}",
        "A required substring.",
    ),
    (
        "trimmed",
        [],
        "value == strip(value)",
        "must not have leading or trailing whitespace",
        "No surrounding whitespace.",
    ),
    (
        "is_lowercase",
        [],
        "value == lower(value)",
        "must be lowercase",
        "No uppercase characters.",
    ),
    (
        "is_uppercase",
        [],
        "value == upper(value)",
        "must be uppercase",
        "No lowercase characters.",
    ),
    (
        "is_identifier",
        [],
        'regex_full_match(value, "[A-Za-z_][A-Za-z0-9_]*")',
        "must be a valid identifier",
        "A programming-language identifier.",
    ),
    (
        "is_email",
        [],
        'regex_full_match(value, "[^@\\\\s]+@[^@\\\\s]+\\\\.[^@\\\\s]+")',
        "must be an email address",
        "An email address, by shape.",
    ),
    (
        "is_url",
        [],
        'regex_full_match(value, "https?://[^\\\\s]+")',
        "must be a URL",
        "An http or https URL, by shape.",
    ),
    (
        "is_uuid",
        [],
        (
            'regex_full_match(value, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-'
            '[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")'
        ),
        "must be a UUID",
        "A canonical UUID string.",
    ),
    (
        "is_country_code",
        [],
        'regex_full_match(value, "[A-Z]{2}")',
        "must be an ISO 3166-1 alpha-2 code",
        "Checks the shape of a country code, not membership of the real list, which changes.",
    ),
    (
        "is_currency_code",
        [],
        'regex_full_match(value, "[A-Z]{3}")',
        "must be an ISO 4217 code",
        "Checks the shape of a currency code, not membership of the real list, which changes.",
    ),
    (
        "no_control_characters",
        [],
        'regex_full_match(value, "[^\\\\x00-\\\\x1f\\\\x7f]*")',
        "must not contain control characters",
        "Excludes control characters.",
    ),
    # numeric
    ("positive", [], "value > 0", "must be positive", "Greater than zero."),
    ("non_negative", [], "value >= 0", "must not be negative", "Zero or greater."),
    ("negative", [], "value < 0", "must be negative", "Less than zero."),
    ("non_positive", [], "value <= 0", "must not be positive", "Zero or less."),
    (
        "multiple_of",
        ["n"],
        "value % n == 0",
        "must be a multiple of {n}",
        (
            "Divisibility. Defined for integer and decimal only; a remainder against "
            "binary floating point has no reliable answer."
        ),
    ),
    (
        "is_finite",
        [],
        "is_finite(value)",
        "must be a finite number",
        "Excludes NaN and infinity, which no backing store accepts.",
    ),
    (
        "max_precision",
        ["p"],
        "precision(value) <= p",
        "must have at most {p} digits",
        (
            "Recognised by the exporter by identity to emit NUMERIC(p, s). "
            "A forked copy is not recognised."
        ),
    ),
    (
        "max_scale",
        ["s"],
        "scale(value) <= s",
        "must have at most {s} decimal places",
        (
            "Recognised by the exporter by identity to emit NUMERIC(p, s). "
            "A forked copy is not recognised."
        ),
    ),
    # temporal — non-deterministic, so no check constraint can carry them
    (
        "in_past",
        [],
        "value < current()",
        "must be in the past",
        "Polymorphic over date and datetime. Not deterministic.",
    ),
    (
        "in_future",
        [],
        "value > current()",
        "must be in the future",
        "Polymorphic over date and datetime. Not deterministic.",
    ),
    (
        "not_in_past",
        [],
        "value >= current()",
        "must not be in the past",
        "Polymorphic over date and datetime. Not deterministic.",
    ),
    (
        "not_in_future",
        [],
        "value <= current()",
        "must not be in the future",
        "Polymorphic over date and datetime. Not deterministic.",
    ),
    # boolean
    ("is_true", [], "value", "must be true", "A boolean that must be set."),
    ("is_false", [], "not value", "must be false", "A boolean that must be clear."),
]

# name, parameters, operand names, message, description
COMPOSITES: list[tuple[str, list[str], str, str, str]] = [
    (
        "non_blank",
        [],
        "non_empty AND trimmed",
        "must not be blank",
        "Non-empty, and no surrounding whitespace.",
    ),
    (
        "is_safe_identifier",
        ["max"],
        "is_identifier AND max_length",
        "must be a short, valid identifier",
        "An identifier within a length limit. Inherits max from max_length.",
    ),
]


def entry(name, parameters, expression, message, description, kind):
    return {
        "uuid": str(builtin_id(name)),
        "name": name,
        "description": description,
        "context": None,
        "kind": kind,
        "parameters": parameters,
        "expression": expression,
        "message": message,
        "created": STAMP,
        "modified": STAMP,
    }


# Passing and failing values for every built-in (validator library §9), in the
# model file's tagged-literal form. A regex that is subtly wrong is the bug this
# library is most prone to, and no reviewer reads a pattern closely enough to
# catch it; one parameterised test over these does. Every built-in must appear.
I, D, S = (
    (lambda v: {"integer": v}),
    (lambda v: {"decimal": v}),
    (lambda v: {"string": v}),
)
R, B = (lambda v: {"real": v}), (lambda v: {"boolean": v})
DATE, DT = (lambda v: {"date": v}), (lambda v: {"datetime": v})
PAST, FUTURE = DATE("2000-01-01"), DATE("2999-01-01")


def L(*values):
    """A list literal of strings."""
    return {"list": {"string": list(values)}}


EXAMPLES: dict[str, tuple[dict, list, list]] = {
    "between": ({"min": I(1), "max": I(9)}, [I(1), I(5), I(9)], [I(0), I(10)]),
    "contains": ({"substring": S("lace")}, [S("Lovelace")], [S("Ada")]),
    "ends_with": ({"suffix": S(".json")}, [S("sales.json")], [S("sales.json.bak")]),
    "equals": ({"other": S("GBP")}, [S("GBP")], [S("gbp")]),
    "exact_length": ({"n": I(2)}, [S("NL")], [S("N"), S("NLD")]),
    "greater_than": ({"min": D("0")}, [D("0.01")], [D("0"), D("-1")]),
    "in_future": ({}, [FUTURE], [PAST]),
    "in_past": ({}, [PAST, DT("2000-01-01T00:00:00Z")], [FUTURE]),
    "is_country_code": ({}, [S("NL"), S("GB")], [S("nl"), S("NLD"), S("N1"), S("")]),
    "is_currency_code": ({}, [S("EUR")], [S("eur"), S("EU"), S("EURO")]),
    "is_email": (
        {},
        [S("ada@example.org")],
        [S("ada@example"), S("ada example@x.org"), S("@example.org"), S("a@@x.org")],
    ),
    "is_false": ({}, [B(False)], [B(True)]),
    "is_finite": ({}, [R(1.5), R(0.0)], [R(float("inf")), R(float("nan"))]),
    "is_identifier": (
        {},
        [S("order_line"), S("_x1")],
        [S("1x"), S("order line"), S("order-line"), S("")],
    ),
    "is_lowercase": ({}, [S("ada"), S("ada 1")], [S("Ada")]),
    "is_safe_identifier": (
        {"max": I(8)},
        [S("order")],
        [S("order_line_total"), S("1x")],
    ),
    "is_true": ({}, [B(True)], [B(False)]),
    "is_uppercase": ({}, [S("GBP"), S("GBP 1")], [S("Gbp")]),
    "is_url": (
        {},
        [S("https://example.org/a?b=1"), S("http://x")],
        [S("ftp://example.org"), S("https://"), S("https://a b")],
    ),
    "is_uuid": (
        {},
        [
            S("5bd36f99-970f-596e-acd8-b907ff8cfa44"),
            S("5BD36F99-970F-596E-ACD8-B907FF8CFA44"),
        ],
        [
            S("5bd36f99970f596eacd8b907ff8cfa44"),
            S("5bd36f99-970f-596e-acd8-b907ff8cfa4"),
            S("not-a-uuid"),
        ],
    ),
    "length_between": (
        {"min": I(2), "max": I(3)},
        [S("ab"), S("abc")],
        [S("a"), S("abcd")],
    ),
    "less_than": ({"max": I(10)}, [I(9)], [I(10)]),
    "matches": (
        {"pattern": S("ORD-[0-9]{6}")},
        [S("ORD-000123")],
        [S("ORD-123"), S("xORD-000123")],
    ),
    "max_length": ({"max": I(3)}, [S(""), S("abc")], [S("abcd")]),
    "max_precision": ({"p": I(6)}, [D("1234.50"), D("0.005")], [D("12345.67")]),
    "max_scale": (
        {"s": I(2)},
        [D("1"), D("1.25"), D("1.20")],
        [D("1.250"), D("0.001")],
    ),
    "max_value": ({"max": I(100)}, [I(100)], [I(101)]),
    "min_length": ({"min": I(2)}, [S("ab")], [S("a")]),
    "min_value": (
        {"min": DATE("2026-01-01")},
        [DATE("2026-01-01")],
        [DATE("2025-12-31")],
    ),
    "multiple_of": ({"n": I(5)}, [I(0), I(15), I(-10)], [I(7)]),
    "negative": ({}, [I(-1)], [I(0), I(1)]),
    "no_control_characters": (
        {},
        [S("plain text"), S("")],
        [S("tab\there"), S("bell\x07")],
    ),
    "non_blank": ({}, [S("Ada")], [S(""), S(" Ada"), S("Ada ")]),
    "non_empty": ({}, [S(" ")], [S("")]),
    "non_negative": ({}, [D("0"), D("0.01")], [D("-0.01")]),
    "non_positive": ({}, [I(0), I(-3)], [I(1)]),
    "not_equals": ({"other": I(0)}, [I(1)], [I(0)]),
    "not_in_future": ({}, [PAST], [FUTURE]),
    "not_in_past": ({}, [FUTURE], [PAST]),
    "not_one_of": ({"options": L("draft", "void")}, [S("sent")], [S("void")]),
    "one_of": (
        {"options": L("low", "normal", "high")},
        [S("low")],
        [S("urgent"), S("Low")],
    ),
    "positive": ({}, [D("0.01")], [D("0")]),
    "starts_with": ({"prefix": S("ORD-")}, [S("ORD-1")], [S("ord-1")]),
    "trimmed": ({}, [S("Ada"), S("")], [S(" Ada"), S("Ada\n")]),
}


def examples() -> dict:
    names = {entry[0] for entry in LEAVES} | {entry[0] for entry in COMPOSITES}
    missing, extra = names - set(EXAMPLES), set(EXAMPLES) - names
    if missing or extra:
        raise SystemExit(
            f"examples out of step: missing {sorted(missing)}, not built-ins {sorted(extra)}"
        )
    return {
        "library_version": LIBRARY_VERSION,
        "examples": {
            name: {"arguments": arguments, "pass": passing, "fail": failing}
            for name, (arguments, passing, failing) in sorted(EXAMPLES.items())
        },
    }


def build() -> dict:
    validators = [entry(*leaf, "leaf") for leaf in LEAVES]
    for name, params, operands, message, description in COMPOSITES:
        # operands are stored as UUIDs and shown as names (spec §5.2)
        expression = operands
        for token in sorted(
            {t for t in operands.split() if t not in {"AND", "OR", "XOR", "NOT"}},
            key=len,
            reverse=True,
        ):
            expression = expression.replace(token, str(builtin_id(token)))
        validators.append(
            entry(name, params, expression, message, description, "composite")
        )
    return {
        "schema_version": 1,
        "library_version": LIBRARY_VERSION,
        "contexts": [],
        "validators": validators,
        "types": [],
        "properties": [],
        "entities": [],
        "schemas": [],
    }


def deprecations() -> dict:
    """Beside the library rather than inside it: the library is an ordinary
    model document, and a model document has nowhere to say "deprecated"."""
    names = {entry[0] for entry in LEAVES} | {entry[0] for entry in COMPOSITES}
    out = []
    for name, replacement, reason in DEPRECATED:
        if name not in names or (replacement is not None and replacement not in names):
            raise SystemExit(
                f"cannot deprecate {name}: it, or its replacement, is not a built-in"
            )
        out.append(
            {
                "validator": str(builtin_id(name)),
                "since": LIBRARY_VERSION,
                **(
                    {"replacement": str(builtin_id(replacement))} if replacement else {}
                ),
                **({"reason": reason} if reason else {}),
            }
        )
    return {"library_version": LIBRARY_VERSION, "deprecated": out}


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    DEPRECATIONS_OUT.write_text(json.dumps(deprecations(), indent=2) + "\n")
    EXAMPLES_OUT.write_text(json.dumps(examples(), indent=2, allow_nan=True) + "\n")
    doc = build()
    print(f"{len(doc['validators'])} built-ins -> {OUT}")
