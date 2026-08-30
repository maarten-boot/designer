"""Attaching a rule to a Type or an Entity.

Headless: which rules fit a value, what each asks for, and what a draft may say
are all decidable without a display — and a dialog that offers the wrong rules
looks perfectly fine on screen.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import Session
from designer_model.expressions.types import UNKNOWN
from designer_model.model import LiteralArg, SlotArg
from designer_model.stdlib import standard_library

from designer_app import bindings

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


@pytest.fixture
def library():
    return standard_library()


def named(items, name):
    return next(i for i in items if i.name == name)


def draft_for(library, name, **kwargs):
    return bindings.BindingDraft(validator=library.by_name(name).uuid, **kwargs)


# --- what value is -----------------------------------------------------------


def test_a_type_supplies_its_own_base_type(session, library) -> None:
    money = named(session.model.types, "Money")
    assert str(bindings.value_type(session.model, money, bindings.BindingDraft())) == "decimal"


def test_an_entity_supplies_the_type_of_a_slot(session, library) -> None:
    order = named(session.model.entities, "Order")
    slot = next(s for s in order.slots if s.slot_name == "total")
    draft = bindings.BindingDraft(slot=slot.uuid)
    assert str(bindings.value_type(session.model, order, draft)) == "decimal"


def test_an_entity_with_no_slot_chosen_knows_nothing_yet(session) -> None:
    order = named(session.model.entities, "Order")
    assert bindings.value_type(session.model, order, bindings.BindingDraft()) is UNKNOWN


def test_an_unfinished_type_keeps_quiet(session) -> None:
    """UNKNOWN rather than an error: an incomplete item should not be showered
    with type failures it cannot yet fix."""
    weight = named(session.model.types, "Weight")
    assert bindings.value_type(session.model, weight, bindings.BindingDraft()) is UNKNOWN


# --- what a rule asks for ----------------------------------------------------


def test_the_same_rule_asks_for_the_type_it_is_applied_to(session, library) -> None:
    """`between` on a decimal wants two decimals; on a date it wants two dates.
    Nothing declares that — it is inferred from the rule's own expression."""
    money = named(session.model.types, "Money")
    wanted = bindings.parameters_for(session.model, library, money, draft_for(library, "between"))
    assert {name: str(kind) for name, kind in wanted.items()} == {
        "min": "decimal",
        "max": "decimal",
    }


def test_a_rule_on_text_asks_for_a_number_where_it_means_one(session, library) -> None:
    short = named(session.model.types, "ShortText")
    wanted = bindings.parameters_for(session.model, library, short, draft_for(library, "max_length"))
    assert {name: str(kind) for name, kind in wanted.items()} == {"max": "integer"}


def test_a_rule_with_no_arguments_asks_for_none(session, library) -> None:
    money = named(session.model.types, "Money")
    assert bindings.parameters_for(session.model, library, money, draft_for(library, "non_negative")) == {}


def test_value_is_never_asked_for(session, library) -> None:
    """It is what the rule is applied *to*, not something to type in."""
    money = named(session.model.types, "Money")
    wanted = bindings.parameters_for(session.model, library, money, draft_for(library, "between"))
    assert "value" not in wanted


# --- which rules are offered -------------------------------------------------


def test_a_rule_that_cannot_apply_is_not_offered(session, library) -> None:
    """The alternative is offering it and then reporting an error the user
    could not have avoided."""
    money = named(session.model.types, "Money")
    empty = bindings.BindingDraft()
    assert not bindings.fits(session.model, library, money, empty, library.by_name("max_length").uuid)
    assert bindings.fits(session.model, library, money, empty, library.by_name("between").uuid)


def test_text_rules_are_offered_for_text(session, library) -> None:
    short = named(session.model.types, "ShortText")
    empty = bindings.BindingDraft()
    assert bindings.fits(session.model, library, short, empty, library.by_name("max_length").uuid)
    assert not bindings.fits(session.model, library, short, empty, library.by_name("max_scale").uuid)


def test_everything_is_offered_while_the_type_is_unknown(session, library) -> None:
    """Nothing is known to contradict, and refusing everything would make an
    unfinished item unworkable."""
    weight = named(session.model.types, "Weight")
    empty = bindings.BindingDraft()
    assert bindings.fits(session.model, library, weight, empty, library.by_name("between").uuid)


# --- what a draft may say ----------------------------------------------------


def test_a_rule_must_be_chosen(session, library) -> None:
    money = named(session.model.types, "Money")
    with pytest.raises(bindings.BindingError, match="choose a rule"):
        bindings.check(session.model, library, money, bindings.BindingDraft())


def test_an_entity_rule_must_name_a_slot(session, library) -> None:
    order = named(session.model.entities, "Order")
    with pytest.raises(bindings.BindingError, match="which slot"):
        bindings.check(session.model, library, order, draft_for(library, "non_negative"))


def test_an_argument_of_the_wrong_type_is_refused(session, library) -> None:
    money = named(session.model.types, "Money")
    draft = draft_for(library, "between", arguments={"min": "nought", "max": "10"})
    with pytest.raises(bindings.BindingError, match="min:"):
        bindings.check(session.model, library, money, draft)


def test_a_missing_argument_is_incomplete_not_wrong(session, library) -> None:
    """An item is filled in as it is made."""
    money = named(session.model.types, "Money")
    bindings.check(session.model, library, money, draft_for(library, "between"))


# --- the commands ------------------------------------------------------------


def test_adding_a_rule_is_one_undo_step(session, library) -> None:
    money = named(session.model.types, "Money")
    before = len(money.validators)
    draft = draft_for(library, "between", arguments={"min": "0.00", "max": "99.99"})
    session.execute(bindings.add(session.model, library, money, draft))
    assert len(money.validators) == before + 1
    assert len(session.stack) == 1
    session.undo()
    assert len(money.validators) == before


def test_arguments_are_stored_as_typed_literals(session, library) -> None:
    """`0.10` on a decimal stays exact; read as a float it would not be."""
    from decimal import Decimal

    money = named(session.model.types, "Money")
    draft = draft_for(library, "between", arguments={"min": "0.10", "max": "99.99"})
    session.execute(bindings.add(session.model, library, money, draft))
    added = money.validators[-1]
    assert isinstance(added.arguments["min"], LiteralArg)
    assert added.arguments["min"].literal.value == Decimal("0.10")


def test_an_entity_rule_records_the_slot(session, library) -> None:
    order = named(session.model.entities, "Order")
    slot = next(s for s in order.slots if s.slot_name == "total")
    draft = draft_for(library, "min_value", slot=slot.uuid, arguments={"min": "1.00"})
    session.execute(bindings.add(session.model, library, order, draft))
    assert order.validators[-1].arguments["value"] == SlotArg(slot.uuid)


def test_editing_a_rule_leaves_it_where_it_was(session, library) -> None:
    """A rule that jumped to the end every time it was edited would reorder
    what the author arranged."""
    money = named(session.model.types, "Money")
    first = money.validators[0]
    draft = bindings.BindingDraft.of(first)
    draft.message = "must not be negative"
    session.execute(bindings.edit(session.model, library, money, first, draft))
    assert money.validators[0].message == "must not be negative"
    assert len(money.validators) == 3


def test_editing_is_one_undo_step(session, library) -> None:
    money = named(session.model.types, "Money")
    first = money.validators[0]
    draft = bindings.BindingDraft.of(first)
    draft.message = "changed"
    session.execute(bindings.edit(session.model, library, money, first, draft))
    session.undo()
    assert money.validators[0].message == first.message


def test_removing_a_rule_puts_it_back_in_place(session, library) -> None:
    money = named(session.model.types, "Money")
    victim = money.validators[1]
    session.execute(bindings.remove(money, victim))
    assert victim not in money.validators
    session.undo()
    assert money.validators[1] is victim


def test_a_round_trip_through_a_draft_changes_nothing(session, library) -> None:
    money = named(session.model.types, "Money")
    for binding in list(money.validators):
        draft = bindings.BindingDraft.of(binding)
        bindings.check(session.model, library, money, draft)


# --- describing --------------------------------------------------------------


def test_a_rule_describes_itself_for_the_table(session, library) -> None:
    money = named(session.model.types, "Money")
    scale = next(b for b in money.validators if library.get(b.validator).name == "max_scale")
    assert bindings.describes(session.model, library, money, scale) == ("max_scale", "", "s=2")


def test_an_entity_rule_names_its_slot(session, library) -> None:
    auditable = named(session.model.entities, "Auditable")
    name, applies, _ = bindings.describes(session.model, library, auditable, auditable.validators[0])
    assert (name, applies) == ("in_past", "created_at")


# --- what a validator accepts ------------------------------------------------


def test_a_validator_may_accept_several_base_types(session, library) -> None:
    """It does not have *a* base type. `between` compares, and comparison is
    defined for seven of the eight."""
    taken = bindings.accepts(session.model, library, library.by_name("between"))
    assert set(taken) >= {"integer", "decimal", "date", "string"}
    assert "boolean" not in taken


def test_a_validator_may_accept_exactly_one(session, library) -> None:
    assert bindings.accepts(session.model, library, library.by_name("max_length")) == ("string",)


def test_a_numeric_rule_takes_the_numeric_types(session, library) -> None:
    assert set(bindings.accepts(session.model, library, library.by_name("non_negative"))) == {
        "integer",
        "real",
        "decimal",
    }


def test_a_rule_that_only_compares_takes_everything(session, library) -> None:
    from designer_model.expressions.types import BASE_TYPES

    assert len(bindings.accepts(session.model, library, library.by_name("equals"))) == len(BASE_TYPES)


def test_a_composite_accepts_what_all_its_operands_do(session, library) -> None:
    """Every operand is applied to the same value, so the composite is only as
    permissive as its narrowest part."""
    composite = named(session.model.validators, "order_reference")
    taken = bindings.accepts(session.model, library, composite)
    assert taken == ("string",)


def test_what_it_accepts_agrees_with_what_it_fits(session, library) -> None:
    """Two routes to the same judgement; they must not disagree."""
    money = named(session.model.types, "Money")
    empty = bindings.BindingDraft()
    for name in ("max_length", "non_negative", "between", "max_scale"):
        candidate = library.by_name(name)
        taken = bindings.accepts(session.model, library, candidate)
        assert bindings.fits(session.model, library, money, empty, candidate.uuid) == ("decimal" in taken), name


# --- cross-entity rules ------------------------------------------------------


def schema_of(session, name="sales_schema"):
    return named(session.model.schemas, name)


def test_an_existing_cross_entity_rule_round_trips(session, library) -> None:
    sales = schema_of(session)
    draft = bindings.SchemaDraft.of(sales.validators[0])
    bindings.schema_check(session.model, library, sales, draft)
    assert set(draft.paths) == {"value", "other"}


def test_value_comes_from_the_path_it_lands_on(session, library) -> None:
    """Unlike the other two sites, a Schema rule has to say *which* value
    before it can say anything about it."""
    sales = schema_of(session)
    draft = bindings.SchemaDraft.of(sales.validators[0])
    assert str(bindings.schema_value_type(session.model, draft)) == "string"


def test_no_path_means_nothing_is_known_yet(session, library) -> None:
    draft = bindings.SchemaDraft()
    assert bindings.schema_value_type(session.model, draft) is UNKNOWN


def test_value_is_one_of_the_paths_to_build(session, library) -> None:
    sales = schema_of(session)
    draft = bindings.SchemaDraft.of(sales.validators[0])
    assert "value" in bindings.schema_parameters(session.model, library, draft)


def test_an_unbuilt_path_is_refused(session, library) -> None:
    sales = schema_of(session)
    draft = bindings.SchemaDraft.of(sales.validators[0])
    draft.paths["other"] = ()
    with pytest.raises(bindings.BindingError, match="other: choose a value"):
        bindings.schema_check(session.model, library, sales, draft)


def test_an_anchor_must_be_chosen(session, library) -> None:
    sales = schema_of(session)
    with pytest.raises(bindings.BindingError, match="anchor"):
        bindings.schema_check(session.model, library, sales, bindings.SchemaDraft())


def test_adding_a_cross_entity_rule_is_one_undo_step(session, library) -> None:
    from designer_app import paths

    sales = schema_of(session)
    order = named(session.model.entities, "Order")
    steps = paths.next_steps(session.model, sales, order.uuid, ())
    total = next(s for s in steps if s.name == "total")
    draft = bindings.SchemaDraft(
        anchor=order.uuid,
        validator=library.by_name("non_negative").uuid,
        paths={"value": (total.slot,)},
    )
    before = len(sales.validators)
    session.execute(bindings.schema_add(session.model, library, sales, draft))
    assert len(sales.validators) == before + 1
    assert len(session.stack) == 1
    session.undo()
    assert len(sales.validators) == before


def test_a_cross_entity_rule_is_never_a_check_constraint(session, library) -> None:
    """A rule spanning two tables cannot be one, whatever anyone claims — so
    the enforcement is not offered as a choice."""
    from designer_app import paths

    sales = schema_of(session)
    order = named(session.model.entities, "Order")
    total = next(s for s in paths.next_steps(session.model, sales, order.uuid, ()) if s.name == "total")
    draft = bindings.SchemaDraft(
        anchor=order.uuid,
        validator=library.by_name("non_negative").uuid,
        paths={"value": (total.slot,)},
    )
    session.execute(bindings.schema_add(session.model, library, sales, draft))
    assert sales.validators[-1].enforcement == "application"


def test_a_cross_entity_rule_describes_itself_as_a_row(session, library) -> None:
    sales = schema_of(session)
    name, anchor, routes, enforced = bindings.schema_describes(session.model, library, sales.validators[0])
    assert (name, anchor, enforced) == ("equals", "OrderLine", "application")
    assert "OrderLine.order.ship_to_country" in routes


def test_editing_a_cross_entity_rule_leaves_it_in_place(session, library) -> None:
    sales = schema_of(session)
    first = sales.validators[0]
    draft = bindings.SchemaDraft.of(first)
    draft.message = "countries must match"
    session.execute(bindings.schema_edit(session.model, library, sales, first, draft))
    assert sales.validators[0].message == "countries must match"
    assert len(sales.validators) == 1


def test_a_rule_added_through_the_editor_checks_clean(session, library) -> None:
    """The editor's rules and the model check must agree."""
    from designer_app import paths

    sales = schema_of(session)
    order = named(session.model.entities, "Order")
    total = next(s for s in paths.next_steps(session.model, sales, order.uuid, ()) if s.name == "total")
    draft = bindings.SchemaDraft(
        anchor=order.uuid,
        validator=library.by_name("non_negative").uuid,
        paths={"value": (total.slot,)},
    )
    session.execute(bindings.schema_add(session.model, library, sales, draft))
    codes = {f.code for f in session.full_check().findings if f.subject.item_uuid == sales.uuid}
    assert not {c for c in codes if c.startswith("MOD5")}, codes
