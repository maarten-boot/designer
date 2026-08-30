"""Paths from an anchor.

Headless. Which step may come next, and why a path is refused, is the whole
substance of the picker — and a picker that offers a step it should not looks
perfectly fine on screen until somebody takes it.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import Session

from designer_app import paths

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


def named(items, name):
    return next(i for i in items if i.name == name)


def schema(session, name="sales_schema"):
    return named(session.model.schemas, name)


def entity(session, name):
    return named(session.model.entities, name)


def step_named(steps, name):
    return next(s for s in steps if s.name == name)


def walk(session, anchor, *names):
    """Follow a route by slot name, as the picker would."""
    path: tuple = ()
    for name in names:
        step = step_named(paths.next_steps(session.model, schema(session), anchor, path), name)
        path = (*path, step.slot)
    return path


# --- anchors -----------------------------------------------------------------


def test_only_members_may_anchor_a_rule(session) -> None:
    offered = {session.model.index()[u].name for u in paths.anchors(session.model, schema(session))}
    assert offered == {"Customer", "Order", "OrderLine"}
    assert "Ticket" not in offered


def test_an_abstract_member_cannot_anchor(session) -> None:
    """It never becomes a table, so there is nothing for the rule to run
    against."""
    sales = schema(session)
    sales.members = (*sales.members, entity(session, "LineItem").uuid)
    offered = {session.model.index()[u].name for u in paths.anchors(session.model, sales)}
    assert "LineItem" not in offered


# --- what may come next ------------------------------------------------------


def test_the_first_step_is_the_anchor_s_own_slots(session) -> None:
    steps = paths.next_steps(session.model, schema(session), entity(session, "Order").uuid, ())
    assert {s.name for s in steps} >= {"customer", "total", "order_number"}


def test_a_reference_continues_and_a_value_ends(session) -> None:
    steps = paths.next_steps(session.model, schema(session), entity(session, "Order").uuid, ())
    assert step_named(steps, "customer").continues
    assert not step_named(steps, "total").continues


def test_a_reference_says_where_it_goes(session) -> None:
    steps = paths.next_steps(session.model, schema(session), entity(session, "Order").uuid, ())
    assert step_named(steps, "customer").reaches == "Customer"


def test_taking_a_reference_offers_the_target_s_slots(session) -> None:
    order = entity(session, "Order").uuid
    path = walk(session, order, "customer")
    steps = paths.next_steps(session.model, schema(session), order, path)
    assert {s.name for s in steps} >= {"country_code", "name"}


def test_a_reference_leaving_the_schema_is_not_offered(session) -> None:
    """The rule has to be checkable within what ships, so a path out of the
    schema is not something to offer and then refuse."""
    sales = schema(session)
    customer = entity(session, "Customer").uuid
    sales.members = tuple(m for m in sales.members if m != customer)
    steps = paths.next_steps(session.model, sales, entity(session, "Order").uuid, ())
    assert "customer" not in {s.name for s in steps if s.continues}


def test_references_stop_being_offered_at_the_limit(session) -> None:
    """Four segments. Beyond that a rule is describing a query rather than a
    constraint."""
    order_line = entity(session, "OrderLine").uuid
    three = walk(session, order_line, "order", "customer")
    steps = paths.next_steps(session.model, schema(session), order_line, three)
    assert any(not s.continues for s in steps), "no value to finish on"
    assert all(not s.continues for s in steps), "a fourth reference was offered"


def test_nothing_follows_a_value(session) -> None:
    order = entity(session, "Order").uuid
    path = walk(session, order, "total")
    assert paths.next_steps(session.model, schema(session), order, path) == []


def test_no_anchor_offers_nothing(session) -> None:
    assert paths.next_steps(session.model, schema(session), None, ()) == []


# --- what a path may be ------------------------------------------------------


def test_a_finished_path_is_accepted(session) -> None:
    order_line = entity(session, "OrderLine").uuid
    path = walk(session, order_line, "order", "customer", "country_code")
    assert paths.problem(session.model, schema(session), order_line, path) is None


def test_a_path_ending_on_a_reference_is_refused(session) -> None:
    order = entity(session, "Order").uuid
    path = walk(session, order, "customer")
    assert "ends on a reference" in paths.problem(session.model, schema(session), order, path)


def test_an_empty_path_is_refused(session) -> None:
    order = entity(session, "Order").uuid
    assert "choose a value" in paths.problem(session.model, schema(session), order, ())


def test_a_path_with_no_anchor_is_refused(session) -> None:
    assert "anchor" in paths.problem(session.model, schema(session), None, ())


def test_an_anchor_that_is_not_a_member_is_refused(session) -> None:
    ticket = entity(session, "Ticket").uuid
    assert "not a member" in paths.problem(session.model, schema(session), ticket, ())


def test_too_many_segments_is_refused(session) -> None:
    order_line = entity(session, "OrderLine").uuid
    path = walk(session, order_line, "order", "customer", "country_code")
    too_long = (*path, path[-1], path[-1])
    assert "limit" in paths.problem(session.model, schema(session), order_line, too_long)


# --- reading one -------------------------------------------------------------


def test_a_path_reads_as_a_route(session) -> None:
    order_line = entity(session, "OrderLine").uuid
    path = walk(session, order_line, "order", "customer", "country_code")
    assert paths.render(session.model, order_line, path) == ("OrderLine.order.customer.country_code")


def test_an_anchor_alone_reads_as_itself(session) -> None:
    assert paths.render(session.model, entity(session, "Order").uuid, ()) == "Order"


def test_a_path_lands_on_the_slot_the_rule_applies_to(session) -> None:
    order_line = entity(session, "OrderLine").uuid
    path = walk(session, order_line, "order", "customer", "country_code")
    assert paths.value_slot(session.model, order_line, path).slot_name == "country_code"


def test_an_unfinished_path_lands_nowhere(session) -> None:
    order = entity(session, "Order").uuid
    assert paths.value_slot(session.model, order, walk(session, order, "customer")) is None
