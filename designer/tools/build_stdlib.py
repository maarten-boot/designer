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

LIBRARY_VERSION = 1
STAMP = "2026-08-29T00:00:00Z"

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
        "An upper length bound.",
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
        "must have at most {p} significant digits",
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


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    doc = build()
    print(f"{len(doc['validators'])} built-ins -> {OUT}")
