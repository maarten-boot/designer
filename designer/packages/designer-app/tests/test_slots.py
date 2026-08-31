"""Editing slots.

Headless. Whether an override narrows, whether a default parses, which types
may be offered — all of it decidable without a display, and none of it visible
by looking at a dialog.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from decimal import Decimal

import pytest
from designer_model import Deriver, Session

from designer_app import forms, slots

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


def entity(session, name):
    return by_name(session.model.entities, name)


def strict_parent(session):
    """Make LineItem's slot the strict one, so OrderLine's would be a widening."""
    positive = by_name(session.model.types, "PositiveMoney")
    parent = next(s for s in entity(session, "LineItem").slots if s.slot_name == "line_total")
    parent.type_override, parent.required = positive.uuid, True
    return Deriver(session.model).inherited_slot(entity(session, "OrderLine").uuid, "line_total")


# --- defaults ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "text", "expected"),
    [
        ("integer", "42", 42),
        ("decimal", "0.10", Decimal("0.10")),
        ("string", "hello", "hello"),
        ("boolean", "true", True),
        ("date", "2026-08-30", dt.date(2026, 8, 30)),
    ],
)
def test_a_default_is_read_as_its_type(base, text, expected) -> None:
    assert slots.parse_default(base, text).value == expected


def test_a_decimal_default_stays_exact() -> None:
    """Read as a float, 0.10 would not be 0.10 — which is the whole reason
    decimal exists."""
    assert slots.parse_default("decimal", "0.10").value == Decimal("0.10")


def test_an_empty_default_is_no_default() -> None:
    assert slots.parse_default("integer", "  ") is None


def test_a_default_needs_a_type_to_be_read_as() -> None:
    with pytest.raises(slots.SlotError, match="type before a default"):
        slots.parse_default(None, "42")


def test_a_default_that_is_not_its_type_is_refused() -> None:
    with pytest.raises(slots.SlotError, match="not a integer"):
        slots.parse_default("integer", "half past three")


def test_a_naive_datetime_default_is_refused() -> None:
    """Datetimes are timezone aware and always UTC."""
    with pytest.raises(slots.SlotError, match="timezone"):
        slots.parse_default("datetime", "2026-08-30T10:00:00")


def test_a_datetime_default_is_normalised_to_utc() -> None:
    parsed = slots.parse_default("datetime", "2026-08-30T12:00:00+02:00")
    assert parsed.value == dt.datetime(2026, 8, 30, 10, 0, tzinfo=dt.UTC)


# --- what a draft may say ----------------------------------------------------


def test_a_slot_needs_a_name(session) -> None:
    with pytest.raises(slots.SlotError, match="needs a name"):
        slots.check(session.model, entity(session, "Order"), slots.SlotDraft(slot_name=" "), None)


def test_two_slots_cannot_share_a_name(session) -> None:
    with pytest.raises(slots.SlotError, match="already has a slot"):
        slots.check(session.model, entity(session, "Order"), slots.SlotDraft(slot_name="total"), None)


def test_a_reference_to_an_abstract_entity_is_refused(session) -> None:
    abstract = entity(session, "Auditable")
    draft = slots.SlotDraft(slot_name="owner", kind=slots.REFERENCE, target=abstract.uuid)
    with pytest.raises(slots.SlotError, match="abstract"):
        slots.check(session.model, entity(session, "Order"), draft, None)


def test_a_required_slot_cannot_be_set_null(session) -> None:
    customer = entity(session, "Customer")
    draft = slots.SlotDraft(
        slot_name="buyer",
        kind=slots.REFERENCE,
        target=customer.uuid,
        required=True,
        on_delete="set_null",
    )
    with pytest.raises(slots.SlotError, match="set null"):
        slots.check(session.model, entity(session, "Order"), draft, None)


def test_an_unset_target_is_allowed(session) -> None:
    """An item is filled in as it is made; incomplete is not wrong."""
    draft = slots.SlotDraft(slot_name="buyer", kind=slots.REFERENCE)
    slots.check(session.model, entity(session, "Order"), draft, None)


# --- overrides ---------------------------------------------------------------


def test_an_override_may_narrow(session) -> None:
    inherited = strict_parent(session)
    own = next(s for s in entity(session, "OrderLine").slots if s.slot_name == "line_total")
    slots.check(session.model, entity(session, "OrderLine"), slots.SlotDraft.of(own), inherited, editing=own)


def test_an_override_may_not_widen(session) -> None:
    inherited = strict_parent(session)
    money = by_name(session.model.types, "Money")
    own = next(s for s in entity(session, "OrderLine").slots if s.slot_name == "line_total")
    draft = slots.SlotDraft.of(own)
    draft.type_override = money.uuid
    with pytest.raises(slots.SlotError, match="narrow"):
        slots.check(session.model, entity(session, "OrderLine"), draft, inherited, editing=own)


def test_an_override_may_not_make_a_required_slot_optional(session) -> None:
    inherited = strict_parent(session)
    own = next(s for s in entity(session, "OrderLine").slots if s.slot_name == "line_total")
    draft = slots.SlotDraft.of(own)
    draft.required = False
    with pytest.raises(slots.SlotError, match="optional"):
        slots.check(session.model, entity(session, "OrderLine"), draft, inherited, editing=own)


def test_an_override_may_not_change_the_kind(session) -> None:
    """The reference branch used to return before the override rules ran, so
    this was allowed."""
    inherited = strict_parent(session)
    own = next(s for s in entity(session, "OrderLine").slots if s.slot_name == "line_total")
    draft = slots.SlotDraft.of(own)
    draft.kind = slots.REFERENCE
    with pytest.raises(slots.SlotError, match="kind of slot"):
        slots.check(session.model, entity(session, "OrderLine"), draft, inherited, editing=own)


# --- the commands ------------------------------------------------------------


def test_adding_a_slot_is_one_undo_step(session) -> None:
    order = entity(session, "Order")
    amount = by_name(session.model.properties, "amount")
    before = len(order.slots)
    draft = slots.SlotDraft(slot_name="discount", property=amount.uuid, required=False)
    session.execute(slots.add(session.model, order, draft))
    assert len(order.slots) == before + 1
    assert len(session.stack) == 1
    session.undo()
    assert len(order.slots) == before


def test_a_new_slot_goes_last(session) -> None:
    order = entity(session, "Order")
    amount = by_name(session.model.properties, "amount")
    session.execute(slots.add(session.model, order, slots.SlotDraft(slot_name="discount", property=amount.uuid)))
    assert max(s.position for s in order.slots) == order.slots[-1].position


def test_editing_several_fields_is_still_one_step(session) -> None:
    """One user action is one undo step, however many of its fields moved."""
    order = entity(session, "Order")
    slot = next(s for s in order.slots if s.slot_name == "total")
    draft = slots.SlotDraft.of(slot)
    draft.slot_name, draft.required = "order_total", False
    session.execute(slots.edit(session.model, order, slot, draft))
    assert slot.slot_name == "order_total" and slot.required is False
    assert len(session.stack) == 1
    session.undo()
    assert slot.slot_name == "total" and slot.required is True


def test_editing_nothing_changes_nothing(session) -> None:
    order = entity(session, "Order")
    slot = next(s for s in order.slots if s.slot_name == "total")
    session.execute(slots.edit(session.model, order, slot, slots.SlotDraft.of(slot)))
    assert slot.slot_name == "total"


def test_removing_a_slot_puts_it_back_in_place(session) -> None:
    order = entity(session, "Order")
    slot = order.slots[1]
    session.execute(slots.remove(order, slot))
    assert slot not in order.slots
    session.undo()
    assert order.slots[1] is slot


def test_moving_a_slot_swaps_positions(session) -> None:
    """Order is stored, so moving is a real change rather than a view setting."""
    order = entity(session, "Order")
    ordered = sorted(order.slots, key=lambda s: s.position)
    first, second = ordered[0], ordered[1]
    session.execute(slots.move(order, first, 1))
    assert first.position > second.position
    session.undo()
    assert first.position < second.position


def test_moving_past_the_end_does_nothing(session) -> None:
    order = entity(session, "Order")
    last = max(order.slots, key=lambda s: s.position)
    before = last.position
    session.execute(slots.move(order, last, 1))
    assert last.position == before


def test_an_override_becomes_a_new_slot_on_the_child(session) -> None:
    ticket = entity(session, "Ticket")
    inherited = Deriver(session.model).inherited_slot(ticket.uuid, "created_at")
    assert inherited is not None
    draft = slots.SlotDraft.of(inherited)
    before = len(ticket.slots)
    session.execute(slots.add(session.model, ticket, draft, inherited=inherited))
    assert len(ticket.slots) == before + 1
    assert any(s.slot_name == "created_at" for s in ticket.slots)


# --- what the pickers offer --------------------------------------------------


def test_only_referenceable_entities_are_offered(session) -> None:
    """An abstract entity has no table to point at, and one without an identity
    has no column to point at — so neither is offered rather than refused."""
    offered = {c.label for c in forms.slot_target_choices(session.model, entity(session, "Order"))}
    assert "Customer" in offered
    assert "Auditable" not in offered
    assert "LineItem" not in offered


def test_an_override_is_offered_only_narrowing_types(session) -> None:
    order_line = entity(session, "OrderLine")
    inherited = Deriver(session.model).inherited_slot(order_line.uuid, "line_total")
    offered = {c.label for c in forms.narrowing_type_choices(session.model, order_line, inherited)}
    assert "PositiveMoney" in offered
    assert "ShortText" not in offered  # unrelated, and would be a widening
    assert "CountryCode" not in offered
    assert "Money" in offered  # the inherited type: a legal no-op


def test_properties_are_offered_from_the_visible_context(session) -> None:
    offered = {c.label for c in forms.slot_property_choices(session.model, entity(session, "Order"))}
    assert "amount" in offered  # common, an ancestor
    assert "subject" not in offered  # support, a sibling


def test_describing_a_slot_names_its_type_or_target(session) -> None:
    order = entity(session, "Order")
    total = next(s for s in order.slots if s.slot_name == "total")
    customer = next(s for s in order.slots if s.slot_name == "customer")
    assert slots.describes(session.model, total) == "Money"
    assert slots.describes(session.model, customer) == "\u2192 Customer"


# --- naming a slot after its property ----------------------------------------


def test_a_blank_slot_name_takes_the_property_name(session) -> None:
    """It is usually the same name, and typing it again is a chore."""
    order = entity(session, "Order")
    amount = by_name(session.model.properties, "amount")
    draft = slots.SlotDraft(property=amount.uuid)
    assert slots.named_after_its_property(session.model, order, draft).slot_name == "amount"


def test_a_name_already_given_is_left_alone(session) -> None:
    order = entity(session, "Order")
    amount = by_name(session.model.properties, "amount")
    draft = slots.SlotDraft(slot_name="discount", property=amount.uuid)
    assert slots.named_after_its_property(session.model, order, draft).slot_name == "discount"


def test_a_name_already_taken_is_not_reused(session) -> None:
    """Two slots called `amount` cannot both exist, and guessing which was
    meant is not the interface's business."""
    order = entity(session, "Order")
    amount = by_name(session.model.properties, "amount")
    order.slots[0].slot_name = "amount"
    draft = slots.SlotDraft(property=amount.uuid)
    assert slots.named_after_its_property(session.model, order, draft).slot_name == ""


def test_a_reference_slot_is_not_named_after_a_property(session) -> None:
    order = entity(session, "Order")
    customer = by_name(session.model.entities, "Customer")
    draft = slots.SlotDraft(kind=slots.REFERENCE, target=customer.uuid)
    assert slots.named_after_its_property(session.model, order, draft).slot_name == ""


def test_a_target_without_an_identity_is_accepted(session) -> None:
    """The model check reports the missing identity; refusing here made a new
    entity unreferenceable."""
    import datetime as dt
    from uuid import uuid4

    from designer_model.model import Entity

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    fresh = Entity(
        uuid=uuid4(),
        name="Invoice",
        description="",
        created=now,
        modified=now,
        context=entity(session, "Order").context,
    )
    session.model.entities.append(fresh)
    draft = slots.SlotDraft(slot_name="invoice", kind=slots.REFERENCE, target=fresh.uuid)
    slots.check(session.model, entity(session, "Order"), draft, None)
