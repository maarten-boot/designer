"""The test bench: what a Type says about a value somebody types.

Reading and judging are separate steps that fail differently, the judging runs
in its own process so a runaway pattern can be stopped, and every rule along
the chain answers — inherited ones first, composites with their operands.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from uuid import uuid4

import pytest

from designer_model import bench, load
from designer_model.bench import FAIL, PASS, UNANSWERED
from designer_model.ids import builtin_id
from designer_model.model import Binding, Interface, InterfaceBinding, Validator

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"
NOW = dt.datetime(2026, 10, 17, tzinfo=dt.UTC)


@pytest.fixture
def model():
    return load(EXAMPLE)


def type_named(model, name):
    return next(t for t in model.types if t.name == name).uuid


def test_a_value_every_rule_passes_is_admitted(model):
    trial = bench.try_value(model, type_named(model, "ShortText"), "Ada")
    assert trial.admitted is True
    assert [(v.rule, v.outcome) for v in trial.verdicts] == [("max_length", PASS), ("non_blank", PASS)]
    assert trial.summary == "read as a string: 'Ada' — the type admits it"


def test_a_composite_shows_each_operand(model):
    trial = bench.try_value(model, type_named(model, "ShortText"), " Ada")
    (non_blank,) = [v for v in trial.verdicts if v.rule == "non_blank"]
    assert non_blank.outcome == FAIL
    assert [(o.rule, o.outcome) for o in non_blank.operands] == [("non_empty", PASS), ("trimmed", FAIL)]


def test_inherited_rules_come_first_and_say_where_they_are_from(model):
    trial = bench.try_value(model, type_named(model, "PositiveMoney"), "0")
    assert [v.origin for v in trial.verdicts] == ["Money", "Money", "Money", "PositiveMoney"]
    (failed,) = [v for v in trial.verdicts if v.outcome == FAIL]
    assert (failed.rule, failed.detail) == ("positive", "must be positive")
    assert trial.admitted is False
    assert trial.summary.endswith("refuses it — 1 of 4 rules fail")


def test_a_failure_uses_the_bindings_own_message(model):
    trial = bench.try_value(model, type_named(model, "ShortText"), "x" * 81)
    (failed,) = [v for v in trial.verdicts if v.outcome == FAIL]
    assert failed.detail == "must be 80 characters or fewer"


def test_a_message_template_gets_its_arguments(model):
    trial = bench.try_value(model, type_named(model, "Money"), "1.234")
    (failed,) = [v for v in trial.verdicts if v.outcome == FAIL]
    assert failed.detail == "must have at most 2 decimal places"


def test_text_that_cannot_be_read_is_not_judged(model):
    trial = bench.try_value(model, type_named(model, "Money"), "abc")
    assert trial.unreadable == "not a decimal"
    assert trial.verdicts == ()
    assert trial.admitted is None
    assert trial.summary == "'abc' cannot be read as a decimal: not a decimal"


def test_text_is_read_through_the_types_interface(model):
    face = Interface(
        uuid=uuid4(),
        name="money_nl",
        description="",
        created=NOW,
        modified=NOW,
        context=model.contexts[0].uuid,
        base_type="decimal",
        picture="#,##0.00",
        decimal_point=",",
        group_mark=".",
    )
    model.interfaces.append(face)
    money = next(t for t in model.types if t.name == "Money")
    money.interfaces.append(InterfaceBinding(uuid=uuid4(), interface=face.uuid))
    # inherited: PositiveMoney reads with Money's interface
    trial = bench.try_value(model, type_named(model, "PositiveMoney"), "1.234,50")
    assert trial.read_as == "with money_nl (#,##0.00)"
    assert trial.value == "1234.50"
    assert trial.admitted is True


def test_a_rule_that_cannot_answer_says_so(model):
    item = next(t for t in model.types if t.name == "ShortText")
    item.validators.append(Binding(uuid=uuid4(), validator=builtin_id("max_length")))  # no `max`
    trial = bench.try_value(model, item.uuid, "Ada")
    assert trial.verdicts[-1].outcome == UNANSWERED
    assert trial.admitted is None


def test_a_type_with_no_base_cannot_read_anything(model):
    trial = bench.try_value(model, type_named(model, "Weight"), "12")
    assert trial.unreadable == "the type has no base type yet"


@pytest.mark.parametrize(
    ("base", "text", "value"),
    [
        ("integer", " 42 ", 42),
        ("boolean", "True", True),
        ("date", "2026-10-17", dt.date(2026, 10, 17)),
        ("datetime", "2026-10-17T12:00:00Z", dt.datetime(2026, 10, 17, 12, tzinfo=dt.UTC)),
    ],
)
def test_literals_are_read_as_the_model_file_writes_them(base, text, value):
    assert bench._read_literal(base, text) == value


def test_a_naive_datetime_is_refused():
    with pytest.raises(bench.ReadError):
        bench._read_literal("datetime", "2026-10-17T12:00:00")


# --- in its own process ------------------------------------------------------


def test_the_separate_process_gives_the_same_answer(model):
    uuid = type_named(model, "PositiveMoney")
    assert bench.run(model, uuid, "12.345") == bench.try_value(model, uuid, "12.345")


def test_a_pattern_that_never_finishes_is_stopped(model):
    evil = Validator(
        uuid=uuid4(),
        name="backtracks",
        description="",
        created=NOW,
        modified=NOW,
        context=model.contexts[0].uuid,
        expression='regex_full_match(value, "(a+)+$")',
        message="never",
    )
    model.validators.append(evil)
    item = next(t for t in model.types if t.name == "ShortText")
    item.validators.append(Binding(uuid=uuid4(), validator=evil.uuid))
    trial = bench.run(model, item.uuid, "a" * 40 + "!", timeout=0.5)
    assert trial.stopped.startswith("no answer within 0.5 s")
    assert trial.admitted is None


def test_a_trial_survives_the_trip_between_processes(model):
    trial = bench.try_value(model, type_named(model, "ShortText"), " Ada")
    assert bench._from_wire(bench._to_wire(trial)) == trial
