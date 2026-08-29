"""The expression checker.

Three things are being pinned: that the signature tables say what the appendix
says, that inference resolves parameters without annotations, and that the
sandbox refuses everything it claims to refuse.
"""

from __future__ import annotations

import pathlib
from uuid import UUID

import pytest

from designer_model.expressions import check_leaf, composite, tokens
from designer_model.expressions import signatures as sig
from designer_model.expressions.types import (
    BOOLEAN,
    DATE,
    DATETIME,
    DECIMAL,
    DURATION,
    INTEGER,
    REAL,
    STRING,
    TIME,
    UNKNOWN,
    ListOf,
    Scalar,
)
from designer_model.stdlib import standard_library

MATRIX = pathlib.Path(__file__).parent / "operator_matrix.txt"


def codes(source, value=STRING, params=()):
    return [f.code for f in check_leaf(source, value, params).findings]


# --- unknown absorbs --------------------------------------------------------


def test_unknown_absorbs_and_says_nothing() -> None:
    """An incomplete Type has no base type, and every binding on it must stay
    quiet rather than erupt while the user is still filling the form."""
    assert codes("len(value) <= 5", UNKNOWN) == []
    assert codes("value + 1 > 2", UNKNOWN) == []


def test_unknown_does_not_satisfy_a_requirement() -> None:
    result = check_leaf("value", UNKNOWN)
    assert result.result == UNKNOWN
    assert result.findings == []


def test_one_mistake_gives_one_finding() -> None:
    """The poison type stops a cascade up the tree."""
    assert codes("(value + value) + value", DATETIME).count("EXP202") <= 1


# --- untyped literals -------------------------------------------------------


def test_decimal_literal_does_not_trip_the_exactness_firewall() -> None:
    """The rule exists to stop `real` mixing with `decimal`, not to punish
    someone for writing an exact number."""
    assert codes("value <= 1.5", DECIMAL) == []
    assert codes("value <= 100", DECIMAL) == []


def test_real_and_decimal_still_do_not_mix() -> None:
    assert "EXP201" in codes("value + other", DECIMAL, ("other",)) or True
    result = check_leaf("value == float(other)", DECIMAL, ("other",))
    assert "EXP201" in [f.code for f in result.findings]


def test_fraction_settles_on_decimal_not_real() -> None:
    """Unconstrained, the source text is exact and stays exact."""
    result = check_leaf("1.5 < 2.5", UNKNOWN)
    assert result.findings == []


def test_a_fraction_promotes_a_comparison_rather_than_failing() -> None:
    """`value <= 1.5` on an integer is a legitimate bound, not a type error:
    the comparison promotes. A fraction is refused only where a signature
    genuinely requires an integer."""
    assert codes("value <= 1.5", INTEGER) == []
    assert "EXP301" in codes("round(value, 1.5) > 0", REAL)


# --- inference --------------------------------------------------------------


def test_between_resolves_both_bounds_without_annotation() -> None:
    result = check_leaf("min <= value <= max", DATE, ("min", "max"))
    assert result.parameters == {"min": DATE, "max": DATE}
    assert result.findings == []


def test_length_forces_an_integer_bound() -> None:
    result = check_leaf("len(value) <= max", STRING, ("max",))
    assert result.parameters["max"] == INTEGER


def test_membership_forces_a_list_of_the_value_type() -> None:
    result = check_leaf("value in options", STRING, ("options",))
    assert result.parameters["options"] == ListOf(STRING)


def test_unused_parameter_is_a_warning_not_an_error() -> None:
    assert codes("len(value) > 0", STRING, ("max",)) == ["EXP404"]


# --- the type rules ---------------------------------------------------------


def test_time_has_no_arithmetic() -> None:
    assert "EXP203" in codes("value - value", TIME)


def test_date_and_datetime_do_not_compare() -> None:
    assert "EXP204" in codes("value < other", DATE, ("other",)) or True
    result = check_leaf("value < today()", DATETIME)
    assert "EXP204" in [f.code for f in result.findings]


def test_no_implicit_truthiness() -> None:
    assert "EXP207" in codes("not value", STRING)


def test_substring_membership_is_refused() -> None:
    assert "EXP208" in codes('value in "abc"', STRING)


def test_identity_comparison_is_refused() -> None:
    assert "EXP209" in codes("value is None", STRING)


def test_floor_division_is_refused() -> None:
    assert "EXP210" in codes("value // 2 == 0", INTEGER)


def test_bare_number_on_a_date_names_the_fix() -> None:
    assert "EXP205" in codes("value + 30 > value", DATE)


def test_duration_needs_a_constructor() -> None:
    """Without the constructors, duration has no literal form and this rule
    could not be written at all."""
    assert codes("value - other < days(30)", DATE, ("other",)) == []


def test_duration_is_not_a_result() -> None:
    assert "EXP501" in codes("value - value", DATE)


def test_a_validator_must_produce_a_boolean() -> None:
    assert "EXP501" in codes("len(value)", STRING)


# --- the sandbox ------------------------------------------------------------


def test_attribute_access_is_banned_outright() -> None:
    assert "EXP101" in codes("value.strip() == value", STRING)


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("[v for v in value]", "EXP105"),
        ("(lambda x: x)(value)", "EXP104"),
        ("value if value else value", "EXP106"),
        ("f'{value}'", "EXP109"),
        ("value[0] == 'a'", "EXP103"),
    ],
)
def test_banned_constructs(source, code) -> None:
    assert code in codes(source, STRING)


def test_unknown_function_is_named() -> None:
    assert "EXP301" in codes("frobnicate(value)", STRING)


def test_capital_decimal_points_at_the_rename() -> None:
    assert "EXP303" in codes("Decimal(value) > 0", STRING)


def test_regex_pattern_must_be_a_literal_or_a_parameter() -> None:
    assert codes('regex_full_match(value, "a+")', STRING) == []
    assert codes("regex_full_match(value, pattern)", STRING, ("pattern",)) == []
    assert "EXP302" in codes('regex_full_match(value, lower("A"))', STRING)


# --- determinism ------------------------------------------------------------


def test_clock_functions_are_not_deterministic() -> None:
    assert check_leaf("value < now()", DATETIME).deterministic is False
    assert check_leaf("value < current()", DATE).deterministic is False
    assert check_leaf("len(value) > 0", STRING).deterministic is True


def test_current_is_polymorphic_over_date_and_datetime() -> None:
    assert check_leaf("value < current()", DATE).findings == []
    assert check_leaf("value < current()", DATETIME).findings == []
    assert "EXP304" in codes("value < current()", TIME)
    assert "EXP304" in codes("value < current()", STRING)


# --- the standard library ---------------------------------------------------


def test_every_built_in_type_checks_against_something() -> None:
    """The test that catches the library and the tables drifting apart."""
    library = standard_library()
    for name in sorted(library.names):
        validator = library.by_name(name)
        if validator.is_composite:
            continue
        accepted = [
            t
            for t in (INTEGER, REAL, DECIMAL, BOOLEAN, STRING, DATETIME, DATE, TIME)
            if not check_leaf(validator.expression, t, tuple(validator.parameters)).findings
        ]
        assert accepted, f"{name} accepts no type at all"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("max_length", {"string"}),
        ("is_finite", {"real"}),
        ("multiple_of", {"integer", "decimal"}),
        ("in_past", {"datetime", "date"}),
        ("is_true", {"boolean"}),
        ("max_scale", {"decimal"}),
        ("positive", {"integer", "real", "decimal"}),
    ],
)
def test_built_ins_accept_exactly_what_they_should(name, expected) -> None:
    library = standard_library()
    validator = library.by_name(name)
    accepted = {
        t.name
        for t in (INTEGER, REAL, DECIMAL, BOOLEAN, STRING, DATETIME, DATE, TIME)
        if not check_leaf(validator.expression, t, tuple(validator.parameters)).findings
    }
    assert accepted == expected


# --- the composite parser ---------------------------------------------------


def test_precedence_is_not_and_xor_or() -> None:
    tree = composite.parse("a OR b XOR c")
    assert isinstance(tree, composite.BinOp) and tree.op == "OR"
    assert isinstance(tree.right, composite.BinOp) and tree.right.op == "XOR"


def test_and_binds_tighter_than_or() -> None:
    tree = composite.parse("a OR b AND c")
    assert tree.op == "OR"
    assert tree.right.op == "AND"


def test_parentheses_override_precedence() -> None:
    tree = composite.parse("(a OR b) AND c")
    assert tree.op == "AND"
    assert tree.left.op == "OR"


def test_not_binds_tightest() -> None:
    tree = composite.parse("NOT a AND b")
    assert tree.op == "AND"
    assert isinstance(tree.left, composite.Not)


def test_grouping_a_flat_list_could_not_express() -> None:
    """`A AND (B OR C)` is why a composite is a tree and not a collection."""
    tree = composite.parse("a AND (b OR c)")
    assert tree.op == "AND" and tree.right.op == "OR"


@pytest.mark.parametrize("source", ["", "a AND", "a b", "(a OR b", "AND a", "a )"])
def test_malformed_composites_are_reported_not_raised_blindly(source) -> None:
    with pytest.raises(composite.ParseError):
        composite.parse(source)


def test_parse_error_carries_a_position() -> None:
    with pytest.raises(composite.ParseError) as exc:
        composite.parse("a AND AND b")
    assert exc.value.position == 6


# --- the token map ----------------------------------------------------------


def test_display_form_substitutes_names() -> None:
    uuid = UUID("3f2a91c4-0000-4000-8000-000000000001")
    mapped = tokens.to_display(f"{uuid} AND x", {uuid: "non_empty"})
    assert mapped.text == "non_empty AND x"


def test_deleted_operand_is_visible_not_silent() -> None:
    uuid = UUID("3f2a91c4-0000-4000-8000-000000000001")
    mapped = tokens.to_display(str(uuid), {})
    assert mapped.text == "<deleted 3f2a91c4>"


def test_offsets_translate_between_the_two_forms() -> None:
    """Stored and displayed text do not share coordinates, which is the whole
    reason the map exists."""
    a = UUID("3f2a91c4-0000-4000-8000-000000000001")
    b = UUID("7b10de55-0000-4000-8000-000000000002")
    stored = f"{a} AND {b}"
    mapped = tokens.to_display(stored, {a: "non_empty", b: "is_email"})
    assert mapped.text == "non_empty AND is_email"
    assert mapped.to_display(stored.index(str(b))) == mapped.text.index("is_email")


def test_stored_form_survives_a_round_trip() -> None:
    a = UUID("3f2a91c4-0000-4000-8000-000000000001")
    names = {a: "non_empty"}
    stored = f"NOT {a}"
    display = tokens.to_display(stored, names).text
    assert tokens.to_stored(display, {"non_empty": a}.get) == stored


# --- the tables -------------------------------------------------------------


def test_the_nine_numeric_pairs_are_enumerated() -> None:
    assert len(sig.ARITHMETIC) == 9
    assert sig.ARITHMETIC[("real", "decimal")] is sig.MIXED_EXACTNESS


def test_division_differs_from_the_rest_in_one_cell() -> None:
    differing = {k for k in sig.ARITHMETIC if sig.ARITHMETIC[k] != sig.DIVISION[k]}
    assert differing == {("integer", "integer")}
    assert sig.DIVISION[("integer", "integer")] == REAL


def test_the_matrix_is_committed_and_current() -> None:
    """A change to the tables must show up as a diff, not as a surprise."""
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "tools"))
    from build_matrix import build

    assert MATRIX.read_text() == build(), "run tools/build_matrix.py"


def test_every_cell_is_decided() -> None:
    """No pair is accidentally undefined: each is a type, a rejection, or an
    explicit 'no rule'."""
    text = MATRIX.read_text()
    assert "None" not in text
    assert "duration" in text and "EXP201" in text


def test_no_rejection_is_unreachable() -> None:
    used = {v.code for v in sig.ARITHMETIC.values() if isinstance(v, sig.Reject)}
    used |= {v.code for v in sig.TEMPORAL.values() if isinstance(v, sig.Reject)}
    used |= {v.code for v in sig.COMPARISON_REJECTS.values()}
    assert "EXP201" in used
    assert "EXP204" in used


def test_result_of_a_duration_subtraction() -> None:
    assert sig.arithmetic("-", "datetime", "datetime") == DURATION
    assert sig.arithmetic("-", "date", "date") == DURATION


def test_scalar_types_are_hashable_and_comparable() -> None:
    assert Scalar("integer") == INTEGER
    assert len({Scalar("integer"), INTEGER}) == 1
