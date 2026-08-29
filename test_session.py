"""Commands, deletion and the session.

All headless: nothing here needs a window, which is the point of putting the
session in the domain package.
"""

from __future__ import annotations

import pathlib
from uuid import uuid4

import pytest

from designer_model.commands import (
    AddItem,
    CommandStack,
    Macro,
    RemoveItem,
    SetField,
    SetSlotField,
)
from designer_model.diagnostics import ConsequenceKind
from designer_model.model import Type
from designer_model.session import Session, read_autosave

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


# --- the stack --------------------------------------------------------------


def test_undo_and_redo_round_trip(session) -> None:
    weight = by_name(session.model.types, "Weight")
    session.execute(SetField(weight.uuid, "name", "Mass"))
    assert weight.name == "Mass"
    session.undo()
    assert weight.name == "Weight"
    session.redo()
    assert weight.name == "Mass"


def test_a_new_action_discards_the_redo_branch(session) -> None:
    weight = by_name(session.model.types, "Weight")
    session.execute(SetField(weight.uuid, "name", "Mass"))
    session.undo()
    assert session.stack.can_redo
    session.execute(SetField(weight.uuid, "description", "something else"))
    assert not session.stack.can_redo


def test_the_stack_is_capped(session) -> None:
    """A single delete can hold an entire subtree, so the stack needs a bound."""
    weight = by_name(session.model.types, "Weight")
    session.stack.limit = 5
    for i in range(20):
        session.execute(SetField(weight.uuid, "description", f"take {i}"))
    assert len(session.stack) == 5


def test_dropping_old_commands_makes_them_unundoable(session) -> None:
    """The second edge the backup file exists to cover."""
    weight = by_name(session.model.types, "Weight")
    session.stack.limit = 2
    for i in range(5):
        session.execute(SetField(weight.uuid, "description", f"take {i}"))
    while session.stack.can_undo:
        session.undo()
    assert weight.description == "take 2"  # not the original


def test_macro_undoes_in_reverse(session) -> None:
    """A delete's fixups must be put back before the item they referred to."""
    order: list[str] = []

    class Noisy(SetField):
        def do(self, model):
            order.append(f"do {self.new}")
            super().do(model)

        def undo(self, model):
            order.append(f"undo {self.new}")
            super().undo(model)

    weight = by_name(session.model.types, "Weight")
    macro = Macro("two", [Noisy(weight.uuid, "name", "A"), Noisy(weight.uuid, "description", "B")])
    session.execute(macro)
    session.undo()
    assert order == ["do A", "do B", "undo B", "undo A"]


def test_remove_restores_position(session) -> None:
    types = session.model.types
    middle = types[3]
    stack = CommandStack(session.model)
    stack.execute(RemoveItem(middle))
    stack.undo()
    assert types[3] is middle


# --- deleting ---------------------------------------------------------------


def test_deleting_a_shared_entity_lists_every_consequence(session) -> None:
    customer = by_name(session.model.entities, "Customer")
    plan = session.plan_delete(customer.uuid)
    grouped = plan.grouped()
    assert len(grouped[ConsequenceKind.MEMBERSHIP_REMOVED]) == 2  # in both schemas
    assert len(grouped[ConsequenceKind.REFERENCE_CLEARED]) == 2  # Order and Ticket


def test_delete_is_one_undo_step(session) -> None:
    """If the fixups were separate, one Ctrl-Z would bring the entity back with
    its references still broken — worse than either state."""
    customer = by_name(session.model.entities, "Customer")
    order = by_name(session.model.entities, "Order")
    slot = next(s for s in order.slots if s.slot_name == "customer")
    session.apply(session.plan_delete(customer.uuid))
    assert slot.target is None
    session.undo()
    assert slot.target == customer.uuid
    assert all(customer.uuid in s.members for s in session.model.schemas)


def test_clearing_an_extension_is_flagged_as_destructive(session) -> None:
    """Losing every inherited slot changes an entity's shape, not just a
    reference, so the dialog has to say so."""
    auditable = by_name(session.model.entities, "Auditable")
    assert session.plan_delete(auditable.uuid).is_destructive
    customer = by_name(session.model.entities, "Customer")
    assert not session.plan_delete(customer.uuid).is_destructive


def test_composite_operand_is_orphaned_not_rewritten(session) -> None:
    """Removing an operand from `A AND B` would change what the rule means."""
    leaf = by_name(session.model.validators, "is_order_number")
    composite = by_name(session.model.validators, "order_reference")
    plan = session.plan_delete(leaf.uuid)
    assert ConsequenceKind.OPERAND_ORPHANED in plan.grouped()
    before = composite.expression
    session.apply(plan)
    assert composite.expression == before  # the UUID stays, visibly broken


def test_deleting_a_context_takes_its_subtree(session) -> None:
    support = by_name(session.model.contexts, "support")
    plan = session.plan_delete(support.uuid)
    names = {session.model.index()[u].name for u in plan.targets}
    assert {"support", "Ticket", "Priority", "support_schema"} <= names


def test_deleting_a_context_is_undoable_whole(session) -> None:
    support = by_name(session.model.contexts, "support")
    before = len(session.model.index())
    session.apply(session.plan_delete(support.uuid))
    assert len(session.model.index()) < before
    session.undo()
    assert len(session.model.index()) == before


def test_the_plan_shown_is_the_plan_applied(session) -> None:
    """One walk produces both, so they cannot drift apart."""
    customer = by_name(session.model.entities, "Customer")
    plan = session.plan_delete(customer.uuid)
    announced = {c.subject.item_uuid for c in plan.consequences}
    # every item the dialog names is an item the command actually touches
    assert announced <= plan.command.touches()
    session.apply(plan)
    assert customer.uuid not in session.model.index()


# --- the session ------------------------------------------------------------


def test_opening_is_not_dirty(session) -> None:
    assert not session.dirty


def test_editing_makes_it_dirty_and_owes_an_autosave(session) -> None:
    weight = by_name(session.model.types, "Weight")
    session.execute(SetField(weight.uuid, "name", "Mass"))
    assert session.dirty and session.autosave_owed


def test_saving_keeps_one_generation_of_backup(session, tmp_path) -> None:
    target = tmp_path / "model.json"
    session.save(target)
    first = target.read_text()
    weight = by_name(session.model.types, "Weight")
    session.execute(SetField(weight.uuid, "name", "Mass"))
    session.save(target)
    assert target.with_suffix(".json.bak").read_text() == first
    assert not session.dirty


def test_autosave_round_trips(session, tmp_path) -> None:
    weight = by_name(session.model.types, "Weight")
    session.execute(SetField(weight.uuid, "name", "Mass"))
    session.write_autosave(tmp_path)
    recovered = read_autosave(tmp_path)
    assert recovered is not None
    assert by_name(recovered.model.types, "Mass")
    assert recovered.path == EXAMPLE


def test_autosave_is_written_atomically(session, tmp_path) -> None:
    session.write_autosave(tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_a_damaged_recovery_file_does_not_prevent_startup(tmp_path) -> None:
    (tmp_path / "autosave.json").write_text("{ this is not json")
    assert read_autosave(tmp_path) is None


def test_no_autosave_means_the_last_session_ended_cleanly(tmp_path) -> None:
    assert read_autosave(tmp_path) is None


def test_clearing_removes_the_recovery_file(session, tmp_path) -> None:
    session.write_autosave(tmp_path)
    session.clear_autosave(tmp_path)
    assert read_autosave(tmp_path) is None


def test_editing_rechecks_incrementally(session) -> None:
    """Model-scope rules are deferred; item-scope ones are not."""
    weight = by_name(session.model.types, "Weight")
    report = session.execute(SetField(weight.uuid, "name", "Mass"))
    assert "MOD101" in report.codes  # item scope, immediate
    assert "MOD601" not in report.codes  # model scope, deferred
    assert "MOD601" in session.full_check().codes


def test_adding_an_item_is_undoable(session) -> None:
    fresh = Type(uuid4(), "Volume", "", session.model.types[0].created, session.model.types[0].modified)
    before = len(session.model.types)
    session.execute(AddItem(fresh))
    assert len(session.model.types) == before + 1
    session.undo()
    assert len(session.model.types) == before


def test_slot_edits_are_separate_steps(session) -> None:
    """Three slot rows are three undo steps, as the granularity rule says."""
    order = by_name(session.model.entities, "Order")
    slots = order.slots[:3]
    for slot in slots:
        session.execute(SetSlotField(order.uuid, slot.uuid, "required", False))
    assert len(session.stack) == 3
    session.undo()
    # only the last step reverted; the first two stand
    assert slots[2].required is True
    assert slots[0].required is False and slots[1].required is False
