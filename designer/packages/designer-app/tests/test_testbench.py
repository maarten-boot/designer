"""The test bench, without a window: which Type is meant, and the rows."""

from __future__ import annotations

import pathlib
from uuid import uuid4

import pytest
from designer_model import bench, load

from designer_app import testbench
from designer_app.selection import Selection, updated

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


def named(items, name):
    return next(i for i in items if i.name == name)


def test_a_type_means_itself_and_a_property_its_type(model):
    money = named(model.types, "Money")
    assert testbench.type_of(model, money.uuid) == money.uuid
    assert testbench.type_of(model, named(model.properties, "amount").uuid) == money.uuid
    assert testbench.type_of(model, named(model.properties, "quantity").uuid) is None
    assert testbench.type_of(model, uuid4()) is None


def test_the_item_in_the_editor_comes_first(model):
    money, short = named(model.types, "Money"), named(model.types, "ShortText")
    selection = updated(updated(Selection(), "type", short.uuid), "property", named(model.properties, "amount").uuid)
    # the property was chosen last, so it is in the editor: its type is meant
    assert testbench.target(model, selection) == money.uuid


def test_with_nothing_typed_selected_there_is_no_target(model):
    selection = updated(Selection(), "entity", named(model.entities, "Order").uuid)
    assert testbench.target(model, selection) is None


def test_a_composite_nests_its_operands(model):
    trial = bench.try_value(model, named(model.types, "ShortText").uuid, " Ada")
    rows = testbench.rows(trial)
    assert [(r.id, r.parent, r.values[0], r.values[2], r.tag) for r in rows] == [
        ("0", "", "max_length", "passes", "pass"),
        ("1", "", "non_blank", "fails", "fail"),
        ("1.0", "1", "non_empty", "passes", "pass"),
        ("1.1", "1", "trimmed", "fails", "fail"),
    ]
    assert rows[1].values[3] == "must not be blank"


def test_an_unreadable_value_has_no_rows(model):
    assert testbench.rows(bench.try_value(model, named(model.types, "Money").uuid, "abc")) == []
