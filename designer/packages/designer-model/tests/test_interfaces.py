"""The Interface item.

How a value is written down for a person and read back, as a thing the model
holds: stored, checked, inherited along the Type chain, and persisted without
disturbing documents that do not use it.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from uuid import uuid4

import pytest

from designer_model import Deriver, check, dump, dumps, load
from designer_model.model import Interface, InterfaceBinding

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


def named(items, name):
    return next(i for i in items if i.name == name)


def add_interface(model, name, base, picture, **kwargs):
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    face = Interface(
        uuid=uuid4(),
        name=name,
        description="",
        created=now,
        modified=now,
        context=model.contexts[0].uuid,
        base_type=base,
        picture=picture,
        **kwargs,
    )
    model.interfaces.append(face)
    return face


def bind(model, type_name, face, default=False):
    item = named(model.types, type_name)
    binding = InterfaceBinding(uuid=uuid4(), interface=face.uuid, is_default=default)
    item.interfaces.append(binding)
    return binding


def codes(model, prefix="INT"):
    return [f.code for f in check(model).findings if f.code.startswith(prefix)]


# --- the document version ----------------------------------------------------


def test_a_model_without_interfaces_stays_at_version_one(model) -> None:
    """Bumping every document on save would strand models that never used the
    feature, for nothing."""
    assert dump(model)["schema_version"] == 1


def test_a_version_one_document_still_round_trips_byte_for_byte(model) -> None:
    assert dumps(model) == EXAMPLE.read_text()


def test_using_an_interface_makes_it_version_two(model) -> None:
    add_interface(model, "money_uk", "decimal", "#,##0.00")
    assert dump(model)["schema_version"] == 2


def test_binding_one_makes_it_version_two_too(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    model.interfaces.clear()
    bind(model, "Money", face)
    assert dump(model)["schema_version"] == 2


def test_a_version_one_document_carries_no_version_two_keys(model) -> None:
    """The shape follows the declared version, or the file is lying about
    itself and an older build meets something it does not know."""
    written = dump(model)
    assert "interfaces" not in written
    assert all("interfaces" not in t for t in written["types"])


def test_a_version_two_document_carries_them(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    written = dump(model)
    assert len(written["interfaces"]) == 1
    assert written["types"][0].get("interfaces") == []


# --- persistence -------------------------------------------------------------


def test_an_interface_round_trips(model) -> None:
    add_interface(model, "german_money", "decimal", "#,##0.00", decimal_point=",", group_mark=".")
    back = load(json.loads(dumps(model)))
    face = named(back.interfaces, "german_money")
    assert (face.base_type, face.picture) == ("decimal", "#,##0.00")
    assert (face.decimal_point, face.group_mark) == (",", ".")


def test_a_binding_round_trips(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    back = load(json.loads(dumps(model)))
    binding = named(back.types, "Money").interfaces[0]
    assert binding.interface == face.uuid
    assert binding.is_default


def test_a_document_with_interfaces_round_trips_exactly(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    text = dumps(model)
    assert dumps(load(json.loads(text))) == text


def test_an_interface_is_in_the_index(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    assert model.index()[face.uuid] is face


# --- checking ----------------------------------------------------------------


def test_an_interface_with_no_base_type_is_unfinished(model) -> None:
    add_interface(model, "unfinished", "", "")
    assert "INT101" in codes(model)


def test_an_interface_with_no_picture_is_unfinished(model) -> None:
    add_interface(model, "unfinished", "decimal", "")
    assert "INT102" in codes(model)


def test_a_bad_picture_is_caught_when_it_is_written(model) -> None:
    """Not when a form renders."""
    add_interface(model, "broken", "decimal", "0.0.0")
    assert "INT201" in codes(model)


def test_a_picture_for_the_wrong_base_type_is_refused(model) -> None:
    face = add_interface(model, "a_date", "date", "dd-MM-yyyy")
    bind(model, "Money", face)
    assert "INT301" in codes(model)


def test_a_matching_base_type_is_accepted(model) -> None:
    """Any decimal Type takes a decimal picture: that is the whole of the
    compatibility rule, and why an Interface needs no hierarchy."""
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face)
    bind(model, "PositiveMoney", face)
    assert "INT301" not in codes(model)


def test_two_defaults_are_refused(model) -> None:
    first = add_interface(model, "one", "decimal", "0.00")
    second = add_interface(model, "two", "decimal", "0.0")
    bind(model, "Money", first, default=True)
    bind(model, "Money", second, default=True)
    assert "INT302" in codes(model)


def test_an_unbound_interface_is_only_a_note(model) -> None:
    from designer_model.codes import definition
    from designer_model.diagnostics import Severity

    add_interface(model, "unused", "string", "X(10)<")
    assert "INT601" in codes(model)
    assert definition("INT601").severity is Severity.INFO


def test_a_bound_interface_is_not_reported_as_unused(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face)
    assert "INT601" not in codes(model)


# --- inheritance along the Type chain ----------------------------------------


def test_a_type_uses_its_own_interface(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    found, origin = Deriver(model).effective_interface(named(model.types, "Money").uuid)
    assert found == face.uuid
    assert origin == named(model.types, "Money").uuid


def test_a_narrowing_type_inherits_from_its_parent(model) -> None:
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    found, origin = Deriver(model).effective_interface(named(model.types, "PositiveMoney").uuid)
    assert found == face.uuid
    assert origin == named(model.types, "Money").uuid, "the origin has to be reported"


def test_the_deepest_binding_wins(model) -> None:
    """Same rule as a narrowing slot: the more specific statement applies."""
    general = add_interface(model, "money_uk", "decimal", "#,##0.00")
    specific = add_interface(model, "money_tight", "decimal", "0.00")
    bind(model, "Money", general, default=True)
    bind(model, "PositiveMoney", specific, default=True)
    found, origin = Deriver(model).effective_interface(named(model.types, "PositiveMoney").uuid)
    assert found == specific.uuid
    assert origin == named(model.types, "PositiveMoney").uuid


def test_a_type_with_nothing_in_its_chain_presents_with_nothing(model) -> None:
    assert Deriver(model).effective_interface(named(model.types, "Money").uuid) is None


def test_the_default_is_chosen_among_several(model) -> None:
    first = add_interface(model, "one", "decimal", "0.00")
    second = add_interface(model, "two", "decimal", "0.0")
    bind(model, "Money", first)
    bind(model, "Money", second, default=True)
    found, _ = Deriver(model).effective_interface(named(model.types, "Money").uuid)
    assert found == second.uuid


# --- deleting one ------------------------------------------------------------


def test_deleting_an_interface_removes_the_bindings(model) -> None:
    """No refusal: the deletion is deliberate, and the useful thing is to say
    what happens next."""
    from designer_model import Session

    session = Session(model)
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    session.apply(session.plan_delete(face.uuid))
    assert named(model.types, "Money").interfaces == []
    assert face.uuid not in model.index()


def test_a_narrowing_type_falls_back_to_its_parent(model) -> None:
    from designer_model import Session

    session = Session(model)
    general = add_interface(model, "money_uk", "decimal", "#,##0.00")
    specific = add_interface(model, "money_tight", "decimal", "0.00")
    bind(model, "Money", general, default=True)
    bind(model, "PositiveMoney", specific, default=True)

    session.apply(session.plan_delete(specific.uuid))
    found, origin = Deriver(model).effective_interface(named(model.types, "PositiveMoney").uuid)
    assert found == general.uuid
    assert origin == named(model.types, "Money").uuid


def test_the_consequence_says_what_it_will_present_with(model) -> None:
    """The outcome, not the mechanism: "a binding was removed" is not what
    somebody needs in order to decide."""
    from designer_model import Session
    from designer_model.diagnostics import ConsequenceKind

    session = Session(model)
    general = add_interface(model, "money_uk", "decimal", "#,##0.00")
    specific = add_interface(model, "money_tight", "decimal", "0.00")
    bind(model, "Money", general, default=True)
    bind(model, "PositiveMoney", specific, default=True)

    plan = session.plan_delete(specific.uuid)
    told = [c for c in plan.consequences if c.kind is ConsequenceKind.PRESENTATION_CHANGED]
    assert len(told) == 1
    assert told[0].args["item"].uuid == general.uuid
    assert told[0].args["origin"].uuid == named(model.types, "Money").uuid


def test_with_nothing_left_in_the_chain_it_says_so(model) -> None:
    """A Type with no presentation is an ordinary state, not a fault — worth
    mentioning, quietly."""
    from designer_model import Session
    from designer_model.diagnostics import ConsequenceKind

    session = Session(model)
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)

    plan = session.plan_delete(face.uuid)
    told = [c for c in plan.consequences if c.kind is ConsequenceKind.PRESENTATION_CHANGED]
    assert told and told[0].args == {}


def test_another_binding_on_the_same_type_wins_over_the_parent(model) -> None:
    from designer_model import Session

    session = Session(model)
    parent = add_interface(model, "money_uk", "decimal", "#,##0.00")
    doomed = add_interface(model, "money_tight", "decimal", "0.00")
    spare = add_interface(model, "money_wide", "decimal", "#,##0.0000")
    bind(model, "Money", parent, default=True)
    bind(model, "PositiveMoney", doomed, default=True)
    bind(model, "PositiveMoney", spare)

    session.apply(session.plan_delete(doomed.uuid))
    found, origin = Deriver(model).effective_interface(named(model.types, "PositiveMoney").uuid)
    assert found == spare.uuid
    assert origin == named(model.types, "PositiveMoney").uuid


def test_deleting_an_interface_is_one_undo_step(model) -> None:
    from designer_model import Session

    session = Session(model)
    face = add_interface(model, "money_uk", "decimal", "#,##0.00")
    bind(model, "Money", face, default=True)
    session.apply(session.plan_delete(face.uuid))
    assert len(session.stack) == 1
    session.undo()
    assert face.uuid in model.index()
    assert len(named(model.types, "Money").interfaces) == 1
