"""Derivation, against the worked example.

These are the computations everything downstream leans on — the model check,
the slot table, the closure action, the export unit — so each is pinned to a
fact in the example rather than to a constructed fixture.
"""

from __future__ import annotations

import pathlib

import pytest

from designer_model import Deriver, load
from designer_model.model import BaseTypeRef

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def d():
    return Deriver(load(EXAMPLE))


def by_name(items, name):
    return next(i for i in items if i.name == name)


# --- contexts ---------------------------------------------------------------


def test_ancestors_are_visible(d) -> None:
    common = by_name(d.model.contexts, "common")
    sales = by_name(d.model.contexts, "sales")
    assert d.is_visible(common.uuid, sales.uuid)


def test_siblings_are_not_visible(d) -> None:
    """sales and support share a parent and cannot see each other (spec §10.1)."""
    sales = by_name(d.model.contexts, "sales")
    support = by_name(d.model.contexts, "support")
    assert not d.is_visible(sales.uuid, support.uuid)
    assert not d.is_visible(support.uuid, sales.uuid)


# --- types ------------------------------------------------------------------


def test_chain_reaches_a_base_type(d) -> None:
    positive = by_name(d.model.types, "PositiveMoney")
    assert d.base_type_of(d.types[positive.uuid].parent) == "decimal"


def test_incomplete_type_has_no_base_type(d) -> None:
    weight = by_name(d.model.types, "Weight")
    assert d.base_type_of(weight.parent) is None


def test_narrowing_is_directional(d) -> None:
    money = by_name(d.model.types, "Money")
    positive = by_name(d.model.types, "PositiveMoney")
    assert d.narrows(positive.uuid, money.uuid)
    assert not d.narrows(money.uuid, positive.uuid)


# --- entities ---------------------------------------------------------------


def test_effective_slots_include_inherited(d) -> None:
    order_line = by_name(d.model.entities, "OrderLine")
    names = {s.slot_name for s in d.effective_slots(order_line.uuid)}
    # created_at from Auditable, id from LineItem, the rest its own
    assert names == {"created_at", "id", "line_total", "order", "quantity"}


def test_override_replaces_rather_than_duplicates(d) -> None:
    order_line = by_name(d.model.entities, "OrderLine")
    line_totals = [s for s in d.effective_slots(order_line.uuid) if s.slot_name == "line_total"]
    assert len(line_totals) == 1
    positive = by_name(d.model.types, "PositiveMoney")
    assert line_totals[0].type_override == positive.uuid
    assert line_totals[0].required is True


def test_override_narrows_the_inherited_slot(d) -> None:
    order_line = by_name(d.model.entities, "OrderLine")
    own = next(s for s in d.entities[order_line.uuid].slots if s.slot_name == "line_total")
    inherited = d.inherited_slot(order_line.uuid, "line_total")
    assert inherited is not None
    assert inherited.required is False and own.required is True
    new_type = d.slot_type(own)
    old_type = d.slot_type(inherited)
    assert d.narrows(new_type.type_uuid, old_type.type_uuid)


def test_identity_is_inherited_not_redeclared(d) -> None:
    order_line = by_name(d.model.entities, "OrderLine")
    line_item = by_name(d.model.entities, "LineItem")
    assert d.entities[order_line.uuid].identity == ()
    assert d.effective_identity(order_line.uuid) == line_item.identity


def test_abstract_entities_have_concrete_descendants(d) -> None:
    for e in d.model.entities:
        if e.abstract:
            assert d.concrete_descendants(e.uuid), f"{e.name} materialises nothing"


def test_slot_type_falls_back_to_the_property(d) -> None:
    customer = by_name(d.model.entities, "Customer")
    created = next(s for s in d.effective_slots(customer.uuid) if s.slot_name == "created_at")
    assert d.slot_type(created) == BaseTypeRef("datetime")


# --- schemas ----------------------------------------------------------------


def test_both_schemas_are_closed(d) -> None:
    for schema in d.model.schemas:
        assert d.unclosed_references(schema) == []


def test_removing_a_member_opens_the_schema(d) -> None:
    sales = by_name(d.model.schemas, "sales_schema")
    customer = by_name(d.model.entities, "Customer")
    sales.members = tuple(m for m in sales.members if m != customer.uuid)
    dangling = d.unclosed_references(sales)
    assert [slot.slot_name for _, slot, _ in dangling] == ["customer"]


def test_membership_is_non_exclusive(d) -> None:
    """Customer belongs to both schemas — the case that drove the design."""
    customer = by_name(d.model.entities, "Customer")
    names = {s.name for s in d.schemas_containing(customer.uuid)}
    assert names == {"sales_schema", "support_schema"}


def test_closure_pulls_in_transitive_references(d) -> None:
    order_line = by_name(d.model.entities, "OrderLine")
    order = by_name(d.model.entities, "Order")
    customer = by_name(d.model.entities, "Customer")
    assert d.closure([order_line.uuid]) == {order_line.uuid, order.uuid, customer.uuid}


def test_path_resolves_through_reference_slots(d) -> None:
    schema = by_name(d.model.schemas, "sales_schema")
    binding = schema.validators[0]
    resolved = d.resolve_path(binding.anchor, binding.arguments["other"].path)
    assert [s.slot_name for s in resolved] == ["order", "customer", "country_code"]
    assert resolved[-1].is_value
    assert all(s.is_reference for s in resolved[:-1])


def test_path_with_a_bad_step_does_not_resolve(d) -> None:
    schema = by_name(d.model.schemas, "sales_schema")
    binding = schema.validators[0]
    customer = by_name(d.model.entities, "Customer")
    bad = (*binding.arguments["other"].path, customer.uuid)
    assert d.resolve_path(binding.anchor, bad) is None


# --- back-references --------------------------------------------------------


def test_references_to_a_shared_entity(d) -> None:
    customer = by_name(d.model.entities, "Customer")
    fields = {field for _, field in d.references_to(customer.uuid)}
    assert "members" in fields  # both schemas list it
    assert any(f.startswith("slots.") for f in fields)  # Order and Ticket point at it


def test_cycles_do_not_hang(d) -> None:
    """A cyclic model is legal to load; the check reports it, nothing hangs."""
    a, b = d.model.entities[1], d.model.entities[2]
    a.extends, b.extends = b.uuid, a.uuid
    assert d.effective_slots(a.uuid) is not None
    assert d.ancestors_of(a.uuid)
    assert d.effective_identity(a.uuid) is not None
