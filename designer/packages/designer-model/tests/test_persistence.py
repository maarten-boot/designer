"""Persistence, against the worked example.

The round trip is the acceptance test for phase 1a: it exercises nullable
references, the typed literal envelope, composite expressions holding operand
UUIDs, binding UUIDs, slot overrides and stored paths in one assertion.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from decimal import Decimal

import pytest

from designer_model import DocumentError, dumps, load
from designer_model.literals import (
    ListLiteral,
    LiteralError,
    ScalarLiteral,
    decode,
    encode,
)

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


def test_round_trip_is_byte_identical(model) -> None:
    assert dumps(model) == EXAMPLE.read_text()


def test_round_trip_is_stable(model) -> None:
    """Saving twice changes nothing — no ordering or formatting drift."""
    once = dumps(model)
    twice = dumps(load(EXAMPLE))
    assert once == twice


def test_counts(model) -> None:
    assert len(model.contexts) == 3
    assert len(model.types) == 8
    assert len(model.entities) == 6
    assert len(model.schemas) == 2


def test_incomplete_item_loads(model) -> None:
    """An unfinished Type must load, not raise (spec §3.1)."""
    weight = next(t for t in model.types if t.name == "Weight")
    assert weight.parent is None


def test_decimal_default_is_exact(model) -> None:
    order = next(e for e in model.entities if e.name == "Order")
    total = next(s for s in order.slots if s.slot_name == "total")
    assert total.default == ScalarLiteral("decimal", Decimal("0.00"))
    assert encode(total.default) == {"decimal": "0.00"}


def test_list_literal_round_trips(model) -> None:
    priority = next(t for t in model.types if t.name == "Priority")
    options = priority.validators[0].arguments["options"].literal
    assert isinstance(options, ListLiteral)
    assert options.values == ("low", "normal", "high", "urgent")


def test_composite_expression_holds_operand_uuids(model) -> None:
    """Stored form is UUIDs; names appear only on display (spec §5.2)."""
    composite = next(v for v in model.validators if v.name == "order_reference")
    leaf = next(v for v in model.validators if v.name == "is_order_number")
    assert str(leaf.uuid) in composite.expression
    assert "is_order_number" not in composite.expression


def test_bindings_have_uuids(model) -> None:
    for t in model.types:
        for b in t.validators:
            assert b.uuid is not None


def test_paths_are_slot_uuids(model) -> None:
    schema = next(s for s in model.schemas if s.name == "sales_schema")
    arg = schema.validators[0].arguments["other"]
    assert len(arg.path) == 3


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(LiteralError):
        decode({"datetime": "2026-08-29T14:30:00"})


def test_offset_datetime_is_normalised_to_utc() -> None:
    literal = decode({"datetime": "2026-08-29T16:30:00+02:00"})
    assert literal.value == dt.datetime(2026, 8, 29, 14, 30, tzinfo=dt.UTC)
    assert encode(literal) == {"datetime": "2026-08-29T14:30:00Z"}


def test_boolean_is_not_an_integer() -> None:
    with pytest.raises(LiteralError):
        decode({"integer": True})


def test_unknown_document_is_rejected() -> None:
    with pytest.raises(DocumentError):
        load({"not": "a model"})


def test_newer_schema_version_is_rejected() -> None:
    with pytest.raises(DocumentError, match="newer"):
        load({"schema_version": 99})
