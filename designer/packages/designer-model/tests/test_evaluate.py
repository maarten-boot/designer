"""Evaluating a rule against one value.

The checker types expressions; this answers them. It is what INT202 uses to
find the values a Type admits, and what a test bench would use to say which
rules a sample passes.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

import pytest

from designer_model.expressions.evaluate import EvaluationError, evaluate_composite, evaluate_leaf
from designer_model.stdlib import standard_library


def builtin(name: str):
    return standard_library().by_name(name)


def test_a_leaf_answers_with_its_arguments():
    assert evaluate_leaf("len(value) <= max", "Ada", {"max": 3})
    assert not evaluate_leaf("len(value) <= max", "Ada!", {"max": 3})


@pytest.mark.parametrize(
    ("name", "value", "arguments", "expected"),
    [
        ("is_country_code", "NL", {}, True),
        ("is_country_code", "nl", {}, False),
        ("max_scale", Decimal("1.25"), {"s": 2}, True),
        ("max_scale", Decimal("1.250"), {"s": 2}, False),
        ("max_precision", Decimal("1234.50"), {"p": 6}, True),
        ("max_precision", Decimal("1234.50"), {"p": 5}, False),
        ("one_of", "low", {"options": ["low", "high"]}, True),
        ("between", 5, {"min": 1, "max": 9}, True),
        ("trimmed", " ada ", {}, False),
        ("non_negative", Decimal("-0.01"), {}, False),
    ],
)
def test_built_ins_answer_as_their_names_say(name, value, arguments, expected):
    assert evaluate_leaf(builtin(name).expression, value, arguments) is expected


def test_current_is_the_clock_in_the_values_own_kind():
    in_past = builtin("in_past").expression
    assert evaluate_leaf(in_past, dt.date(1999, 1, 1))
    assert evaluate_leaf(in_past, dt.datetime(1999, 1, 1, tzinfo=dt.UTC))
    assert not evaluate_leaf(in_past, dt.date(2999, 1, 1))


def test_banned_constructs_are_refused_before_anything_runs():
    with pytest.raises(EvaluationError, match="attribute"):
        evaluate_leaf("value.__class__ == value", "x")
    with pytest.raises(EvaluationError):
        evaluate_leaf("__import__('os') == value", "x")


def test_no_builtins_are_reachable():
    with pytest.raises(EvaluationError):
        evaluate_leaf("print(value) == value", "x")


def test_an_unanswerable_question_is_an_error_not_a_verdict():
    with pytest.raises(EvaluationError):
        evaluate_leaf("len(value) <= max", 42, {"max": 3})
    with pytest.raises(EvaluationError):
        evaluate_leaf("len(value) <= max", "Ada")  # max unset
    with pytest.raises(EvaluationError, match="yes or no"):
        evaluate_leaf("len(value)", "Ada")


@pytest.mark.parametrize(
    ("source", "a", "b", "expected"),
    [
        ("{a} AND {b}", True, False, False),
        ("{a} OR {b}", True, False, True),
        ("{a} XOR {b}", True, True, False),
        ("NOT {a} XOR {b}", False, False, True),
    ],
)
def test_composites_use_their_own_operators(source, a, b, expected):
    first, second = uuid4(), uuid4()
    answers = {first: a, second: b}
    expression = source.format(a=first, b=second)
    assert evaluate_composite(expression, answers.__getitem__) is expected


def test_every_operand_is_asked_even_past_a_short_circuit():
    first, second = uuid4(), uuid4()
    asked = []

    def verdict(uuid):
        asked.append(uuid)
        return False

    evaluate_composite(f"{first} AND {second}", verdict)
    assert asked == [first, second]


def test_a_fraction_literal_is_an_exact_decimal():
    # signature table §4: untyped, exact, decimal unless the context is real
    assert evaluate_leaf("value == 0.1", Decimal("0.1"))
    assert evaluate_leaf("value + 0.5 > 1", Decimal("0.75"))
    assert evaluate_leaf("value * 1.1 == 1.1", 1)


def test_a_fraction_literal_stays_binary_for_a_real():
    assert evaluate_leaf("value == 0.1", 0.1)
    assert evaluate_leaf("value + 0.5 > 1", 0.75)


@pytest.mark.parametrize(
    ("source", "value"),
    [
        ("float(value) + 0.5 > 1", "1"),
        ("(0.5 + 1) * float(value) == 3", "2"),
        ("value <= 0.1", 0.1),
        ("-0.5 < value", Decimal("0")),
    ],
)
def test_a_fraction_literal_meets_a_real_as_a_real(source, value) -> None:
    assert evaluate_leaf(source, value)
