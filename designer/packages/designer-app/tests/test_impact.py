"""What a delete would do, in words.

Headless: the grouping, the wording, and which case counts as destructive are
all decidable without a display — and none of them is checkable by looking at a
dialog.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from designer_model import Session
from designer_model.diagnostics import ConsequenceKind

from designer_app import impact

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


def impact_of(session, name, group=None):
    pool = group or [
        *session.model.contexts,
        *session.model.validators,
        *session.model.types,
        *session.model.properties,
        *session.model.entities,
        *session.model.schemas,
    ]
    item = by_name(pool, name)
    return impact.summarise(session.model, session.plan_delete(item.uuid))


# --- grouping ----------------------------------------------------------------


def test_consequences_are_grouped_not_listed(session) -> None:
    """ "17 items reference this" is not a decision aid; "2 schemas lose a
    member, 2 slots lose their target" is."""
    result = impact_of(session, "Customer")
    kinds = {group.kind for group in result.groups}
    assert kinds == {ConsequenceKind.MEMBERSHIP_REMOVED, ConsequenceKind.REFERENCE_CLEARED}
    assert result.affected == 4


def test_each_line_names_what_it_affects(session) -> None:
    result = impact_of(session, "Customer")
    lines = [line for group in result.groups for line in group.lines]
    assert any("sales_schema" in line for line in lines)
    assert any("Order" in line and "slot customer" in line for line in lines)


def test_losing_an_inheritance_is_marked_destructive(session) -> None:
    """It changes an entity's shape rather than leaving a hole."""
    result = impact_of(session, "Auditable")
    assert result.destructive
    group = next(g for g in result.groups if g.destructive)
    assert len(group.lines) == 4


def test_an_ordinary_delete_is_not_destructive(session) -> None:
    assert not impact_of(session, "Customer").destructive


def test_the_destructive_group_is_listed_first(session) -> None:
    """What loses structure reads before what merely loses a reference."""
    result = impact_of(session, "Auditable")
    assert result.groups[0].destructive


def test_something_nothing_refers_to_says_so(session) -> None:
    result = impact_of(session, "Weight")
    assert result.groups == []
    assert result.summary() == "Nothing else refers to it."


def test_an_orphaned_operand_is_reported(session) -> None:
    """Deleting a validator used in a composite leaves the identity in the
    expression, because only the author can decide what the rule should become."""
    result = impact_of(session, "is_order_number")
    assert result.groups[0].kind is ConsequenceKind.OPERAND_ORPHANED
    assert "order_reference" in result.groups[0].lines[0]


# --- wording -----------------------------------------------------------------


def test_the_summary_counts_correctly(session) -> None:
    assert impact_of(session, "Customer").summary() == ("2 schemas losing a member; 2 slots losing their target")


def test_one_of_something_reads_as_one(session) -> None:
    assert impact_of(session, "is_order_number").summary().startswith("1 expression is")


def test_what_is_removed_is_counted_by_kind(session) -> None:
    assert impact_of(session, "Customer").removing == ("1 entity",)


def test_awkward_plurals_are_spelled_out(session) -> None:
    result = impact_of(session, "support", session.model.contexts)
    assert "2 properties" in result.removing
    assert not any("propertys" in part for part in result.removing)


# --- deleting a context ------------------------------------------------------


def test_a_context_takes_its_whole_subtree(session) -> None:
    result = impact_of(session, "support", session.model.contexts)
    assert set(result.removing) == {"1 context", "1 entity", "2 properties", "1 schema", "1 type"}


def test_the_subtree_is_shown_not_counted(session) -> None:
    """A count is not enough: the whole subtree disappears, and the only honest
    way to show that is to show it."""
    result = impact_of(session, "support", session.model.contexts)
    assert result.subtree is not None
    document = json.loads(result.subtree)
    assert {row["name"] for row in document["entities"]} == {"Ticket"}
    assert {row["name"] for row in document["contexts"]} == {"support"}


def test_the_subtree_holds_nothing_that_survives(session) -> None:
    result = impact_of(session, "support", session.model.contexts)
    document = json.loads(result.subtree)
    assert "Customer" not in {row["name"] for row in document["entities"]}


def test_deleting_one_item_needs_no_subtree(session) -> None:
    assert impact_of(session, "Customer").subtree is None


def test_the_title_names_what_is_going(session) -> None:
    assert impact_of(session, "Customer").title == "Delete Customer?"
    assert impact_of(session, "support", session.model.contexts).title == "Delete support?"


# --- deleting an interface ---------------------------------------------------


def interfaces_on(session):
    """A parent presentation and a narrower one on the type that inherits."""
    import datetime as dt
    from uuid import uuid4

    from designer_model.model import Interface, InterfaceBinding

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    made = []
    for name, picture in (("money_uk", "#,##0.00"), ("money_tight", "0.00")):
        face = Interface(
            uuid=uuid4(),
            name=name,
            description="",
            created=now,
            modified=now,
            context=session.model.contexts[0].uuid,
            base_type="decimal",
            picture=picture,
        )
        session.model.interfaces.append(face)
        made.append(face)
    for type_name, face in (("Money", made[0]), ("PositiveMoney", made[1])):
        by_name(session.model.types, type_name).interfaces.append(
            InterfaceBinding(uuid=uuid4(), interface=face.uuid, is_default=True)
        )
    return made


def test_the_impact_says_what_will_present_instead(session) -> None:
    _general, specific = interfaces_on(session)
    result = impact.summarise(session.model, session.plan_delete(specific.uuid))
    line = result.groups[0].lines[0]
    assert "PositiveMoney" in line
    assert "will present with money_uk" in line
    assert "from Money" in line


def test_the_impact_says_when_nothing_will_remain(session) -> None:
    general, _specific = interfaces_on(session)
    by_name(session.model.types, "PositiveMoney").interfaces.clear()
    result = impact.summarise(session.model, session.plan_delete(general.uuid))
    assert "no presentation will remain" in result.groups[0].lines[0]


def test_losing_a_presentation_is_not_destructive(session) -> None:
    """It changes how a value is written down, not what any entity is."""
    _general, specific = interfaces_on(session)
    assert not impact.summarise(session.model, session.plan_delete(specific.uuid)).destructive
