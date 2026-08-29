"""Changing what a schema contains.

Nothing joins a schema by itself, and adding one entity usually means adding
more than one — a member referencing a non-member leaves the schema unclosed.
One walk produces both what the user is shown and the command that does it.
"""

from __future__ import annotations

import pathlib

import pytest

from designer_model import Session
from designer_model import membership as mb

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


def uuid_of(model, kind, name):
    return by_name(getattr(model, kind), name).uuid


# --- what may join ----------------------------------------------------------


def test_only_concrete_entities_may_join(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    candidates = set(mb.addable(model, schema.uuid))
    assert uuid_of(model, "entities", "Auditable") not in candidates
    assert uuid_of(model, "entities", "Order") in candidates


def test_existing_members_are_not_offered_again(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    for member in schema.members:
        assert member not in mb.addable(model, schema.uuid)


def test_a_sibling_context_is_out_of_reach(session) -> None:
    """support and sales share a parent and cannot see each other."""
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    assert uuid_of(model, "entities", "Ticket") not in mb.addable(model, schema.uuid)


# --- adding -----------------------------------------------------------------


def test_adding_pulls_in_what_the_references_need(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "OrderLine"))
    names = {by_name(model.entities, n).uuid for n in ("OrderLine", "Order", "Customer")}
    assert set(plan.added) == names


def test_the_cascade_is_named_before_it_happens(session) -> None:
    """Adding one entity can cascade into several, and the user sees which."""
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "OrderLine"))
    assert plan.added[0] == uuid_of(model, "entities", "OrderLine")
    assert len(plan.pulled_in) == 2


def test_adding_something_self_contained_pulls_in_nothing(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "Customer"))
    assert plan.pulled_in == ()


def test_adding_an_existing_member_changes_nothing(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_add(model, schema.uuid, schema.members[0])
    assert not plan.changes


def test_an_unreachable_entity_is_blocked_with_a_reason(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "Ticket"))
    assert not plan.changes
    assert plan.blocked and plan.blocked[0][1] == mb.NOT_VISIBLE


def test_an_abstract_entity_is_blocked(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "Auditable"))
    assert not plan.changes
    assert plan.blocked[0][1] == mb.ABSTRACT


def test_adding_is_one_undo_step(session) -> None:
    """A fix the user has to undo ten times is worse than no fix."""
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    plan = mb.plan_add(model, schema.uuid, uuid_of(model, "entities", "OrderLine"))
    session.execute(plan.command())
    assert len(schema.members) == 3
    assert len(session.stack) == 1
    session.undo()
    assert schema.members == ()


# --- removing ---------------------------------------------------------------


def test_removing_names_what_would_dangle(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_remove(model, schema.uuid, uuid_of(model, "entities", "Customer"))
    assert [(slot,) for _, slot, _ in plan.dangling] == [("customer",)]


def test_removing_a_leaf_dangles_nothing(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_remove(model, schema.uuid, uuid_of(model, "entities", "OrderLine"))
    assert plan.dangling == ()


def test_removing_does_not_touch_the_model_until_applied(session) -> None:
    """A plan is a proposal. Nothing changes until its command runs."""
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    before = schema.members
    mb.plan_remove(model, schema.uuid, before[0])
    assert schema.members == before


def test_removing_a_non_member_changes_nothing(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    plan = mb.plan_remove(model, schema.uuid, uuid_of(model, "entities", "Ticket"))
    assert not plan.changes


# --- closing ----------------------------------------------------------------


def test_closing_adds_everything_the_members_reference(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    customer = uuid_of(model, "entities", "Customer")
    schema.members = tuple(m for m in schema.members if m != customer)
    plan = mb.plan_close(model, schema.uuid)
    assert plan.added == (customer,)


def test_closing_a_closed_schema_does_nothing(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    assert not mb.plan_close(model, schema.uuid).changes


def test_closing_leaves_the_schema_closed(session) -> None:
    from designer_model import Deriver

    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = (uuid_of(model, "entities", "OrderLine"),)
    session.execute(mb.plan_close(model, schema.uuid).command())
    assert Deriver(model).unclosed_references(schema) == []


def test_an_unknown_schema_is_refused(session) -> None:
    from uuid import uuid4

    with pytest.raises(KeyError):
        mb.addable(session.model, uuid4())


def test_declining_the_cascade_keeps_the_entity_asked_for(session) -> None:
    """Declining is not cancelling: the named entity joins, and the schema is
    left unclosed rather than the addition being refused."""
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    order_line = uuid_of(model, "entities", "OrderLine")
    plan = mb.plan_add(model, schema.uuid, order_line).only_named()
    assert plan.added == (order_line,)
    assert plan.members_after == (order_line,)


def test_declining_an_addition_with_nothing_to_cascade(session) -> None:
    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    customer = uuid_of(model, "entities", "Customer")
    plan = mb.plan_add(model, schema.uuid, customer)
    assert plan.only_named() is plan


def test_declining_leaves_the_schema_unclosed(session) -> None:
    from designer_model import Deriver

    model = session.model
    schema = by_name(model.schemas, "sales_schema")
    schema.members = ()
    order_line = uuid_of(model, "entities", "OrderLine")
    session.execute(mb.plan_add(model, schema.uuid, order_line).only_named().command())
    assert Deriver(model).unclosed_references(schema)
