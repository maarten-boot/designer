"""The model check.

The acceptance test was written before this code existed: `designer-check.py`,
the prototype built against the specification documents, produced a known set of
codes for the example and for four deliberately broken variants. This suite
pins the same answers.
"""

from __future__ import annotations

import copy
import pathlib
from uuid import uuid4

import pytest

from designer_model import Deriver, load
from designer_model.check import Checker, check
from designer_model.codes import REGISTRY, blocks_export, definition
from designer_model.diagnostics import ItemRef, Scope, Severity, render
from designer_model.ids import builtin_id
from designer_model.model import Binding, PathArg, SlotArg

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"

# The three findings the example is built to produce, and nothing else.
BASELINE = {"MOD602", "MOD101", "MOD601"}


@pytest.fixture
def model():
    return load(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


def new_codes(model) -> set[str]:
    """Codes a mutation introduced, ignoring the deliberate baseline."""
    return set(check(model).codes) - BASELINE


# --- the example ------------------------------------------------------------


def test_example_produces_exactly_the_baseline(model) -> None:
    assert set(check(model).codes) == BASELINE


def test_example_has_no_errors(model) -> None:
    assert check(model).errors == ()


def test_incomplete_blocks_export_but_not_saving(model) -> None:
    report = check(model)
    assert [f.code for f in report.export_blockers] == ["MOD101"]
    assert report.counts()[Severity.ERROR] == 0


def test_findings_render_without_placeholders(model) -> None:
    report = check(model)
    names = {i.uuid: i.name for i in model.entities + model.types + model.validators}
    for finding in report.findings:
        text = render(definition(finding.code).template, finding.args, names)
        assert "{" not in text, f"{finding.code}: {text}"


def test_finding_identity_is_stable(model) -> None:
    """Same input, same keys — which is what lets an incremental re-check
    replace findings in place instead of rebuilding the list."""
    assert [f.key for f in check(model).findings] == [f.key for f in check(model).findings]


# --- the four ported variants ----------------------------------------------


def test_widening_an_inherited_slot(model) -> None:
    """The prototype's MOD412 and MOD413, preserved."""
    positive = by_name(model.types, "PositiveMoney")
    line_item = by_name(model.entities, "LineItem")
    order_line = by_name(model.entities, "OrderLine")
    parent_slot = next(s for s in line_item.slots if s.slot_name == "line_total")
    parent_slot.type_override, parent_slot.required = positive.uuid, True
    child_slot = next(s for s in order_line.slots if s.slot_name == "line_total")
    child_slot.type_override, child_slot.required = None, False
    assert {"MOD412", "MOD413"} <= new_codes(model)


def test_removing_a_member_opens_the_schema_and_breaks_a_path(model) -> None:
    """Two rules that never reference each other, both firing: closure-on-add
    exists precisely so the path rule is rarely what fires first."""
    customer = by_name(model.entities, "Customer")
    sales = by_name(model.schemas, "sales_schema")
    sales.members = tuple(m for m in sales.members if m != customer.uuid)
    codes = new_codes(model)
    assert "MOD503" in codes
    assert "MOD509" in codes


def test_reference_to_an_abstract_entity(model) -> None:
    line_item = by_name(model.entities, "LineItem")
    order_line = by_name(model.entities, "OrderLine")
    next(s for s in order_line.slots if s.slot_name == "order").target = line_item.uuid
    assert "MOD401" in new_codes(model)


def test_path_traversing_a_value_slot(model) -> None:
    customer = by_name(model.entities, "Customer")
    name_slot = next(s for s in customer.slots if s.slot_name == "name")
    sales = by_name(model.schemas, "sales_schema")
    binding = sales.validators[0]
    # PathArg is frozen, so extend by rebuilding it
    binding.arguments["other"] = PathArg((*binding.arguments["other"].path, name_slot.uuid))
    assert "MOD508" in new_codes(model)


# --- sibling contexts -------------------------------------------------------


def test_member_from_a_sibling_context(model) -> None:
    order = by_name(model.entities, "Order")
    support = by_name(model.schemas, "support_schema")
    support.members = (*support.members, order.uuid)
    assert "MOD502" in new_codes(model)


# --- rules the prototype did not have ---------------------------------------


def test_duplicate_name_names_the_other_one(model) -> None:
    money = by_name(model.types, "Money")
    weight = by_name(model.types, "Weight")
    weight.name = money.name
    finding = next(f for f in check(model).findings if f.code == "MOD301")
    assert finding.related and finding.related[0].role == "conflicts_with"


def test_shadowing_an_ancestor(model) -> None:
    common = by_name(model.contexts, "common")
    sales = by_name(model.contexts, "sales")
    shadow = copy.deepcopy(by_name(model.types, "Money"))
    shadow.context, shadow.uuid = sales.uuid, uuid4()
    model.types.append(shadow)
    assert common.uuid != sales.uuid
    assert "MOD302" in new_codes(model)


def test_shadowing_a_builtin(model) -> None:
    by_name(model.validators, "is_order_number").name = "max_length"
    assert "MOD304" in new_codes(model)


def test_unknown_builtin_is_a_library_error(model) -> None:
    money = by_name(model.types, "Money")
    money.validators[0].validator = builtin_id("no_such_builtin")
    assert "LIB101" in new_codes(model)


def test_deleted_composite_operand(model) -> None:
    """Spec §11.1: the UUID stays in the text and becomes a finding, because
    removing an operand from `A AND B` would change what the rule means."""
    leaf = by_name(model.validators, "is_order_number")
    model.validators.remove(leaf)
    assert "MOD113" in new_codes(model)


def test_extension_cycle_is_reported_not_hung(model) -> None:
    a, b = by_name(model.entities, "Order"), by_name(model.entities, "OrderLine")
    a.extends, b.extends = b.uuid, a.uuid
    assert "MOD202" in new_codes(model)


def test_set_null_on_a_required_slot(model) -> None:
    order = by_name(model.entities, "Order")
    slot = next(s for s in order.slots if s.slot_name == "customer")
    slot.on_delete = "set_null"
    assert "MOD411" in new_codes(model)


def test_entity_rule_bound_to_a_reference_slot(model) -> None:
    order_line = by_name(model.entities, "OrderLine")
    order_slot = next(s for s in order_line.slots if s.slot_name == "order")
    order_line.validators.append(Binding(uuid4(), builtin_id("non_empty"), {"value": SlotArg(order_slot.uuid)}))
    assert "MOD414" in new_codes(model)


def test_identity_redeclared_below_an_ancestor(model) -> None:
    order_line = by_name(model.entities, "OrderLine")
    d = Deriver(model)
    order_line.identity = (d.effective_slots(order_line.uuid)[0].uuid,)
    assert "MOD409" in new_codes(model)


# --- the registry -----------------------------------------------------------


def test_every_code_used_is_registered(model) -> None:
    for code in check(model).codes:
        assert code in REGISTRY


def test_export_gating_is_declarative() -> None:
    assert blocks_export("MOD101")
    assert blocks_export("MOD503")
    assert not blocks_export("MOD601")


def test_severity_belongs_to_the_code_not_the_finding() -> None:
    for code, defined in REGISTRY.items():
        assert isinstance(defined.severity, Severity), code
        assert defined.template, code
        assert defined.title, code


def test_scopes_are_assigned() -> None:
    assert {d.scope for d in REGISTRY.values()} <= set(Scope)


def test_incremental_skips_model_scope(model) -> None:
    """Model-scope rules are the deferrable ones; none is urgent while typing."""
    incremental = Checker(model).run_incremental(touched=set())
    assert "MOD601" not in incremental.codes  # model scope, deferred
    assert "MOD101" in incremental.codes  # item scope, immediate


def test_item_refs_are_not_names(model) -> None:
    """A finding must not bake in a name it could outlive."""
    for finding in check(model).findings:
        for value in finding.args.values():
            if isinstance(value, ItemRef):
                assert value.uuid is not None


def test_a_widening_override_names_both_types(model) -> None:
    """ "Widens the inherited type" is a verdict. Which type was inherited and
    which was chosen is what lets somebody fix it."""
    from dataclasses import replace
    from uuid import uuid4

    from designer_model.codes import definition
    from designer_model.diagnostics import render

    line = next(e for e in model.entities if e.name == "LineItem")
    order_line = next(e for e in model.entities if e.name == "OrderLine")
    short_text = next(t for t in model.types if t.name == "ShortText")
    inherited = next(s for s in line.slots if s.is_value)
    order_line.slots.append(replace(inherited, uuid=uuid4(), type_override=short_text.uuid))

    from designer_model import check as run_check

    finding = next(f for f in run_check(model).findings if f.code == "MOD413")
    names = {i.uuid: getattr(i, "name", "") for i in model.index().values()}
    message = render(definition("MOD413").template, finding.args, names)
    assert "ShortText" in message, "the chosen type is not named"
    assert "Uuid" in message, "the inherited type is not named"
    assert "parent chain" in message, "it does not say what would make it legal"


def test_narrowing_an_override_is_accepted(model) -> None:
    """PositiveMoney has Money in its chain, so it restricts rather than widens."""
    from dataclasses import replace
    from uuid import uuid4

    line = next(e for e in model.entities if e.name == "LineItem")
    order_line = next(e for e in model.entities if e.name == "OrderLine")
    money = next(t for t in model.types if t.name == "Money")
    positive = next(t for t in model.types if t.name == "PositiveMoney")
    inherited = next(s for s in line.slots if s.is_value)
    inherited.type_override = money.uuid
    order_line.slots.append(replace(inherited, uuid=uuid4(), type_override=positive.uuid))

    from designer_model import check as run_check

    assert not [f for f in run_check(model).findings if f.code == "MOD413"]


def test_a_reference_to_an_extended_entity_names_what_extends_it(model) -> None:
    """ "Not its descendants'" leaves the reader hunting for which entity that
    is. The check already knows."""
    from dataclasses import replace
    from uuid import uuid4

    from designer_model import check as run_check
    from designer_model.codes import definition
    from designer_model.diagnostics import render

    order = next(e for e in model.entities if e.name == "Order")
    model.entities.append(replace(order, uuid=uuid4(), name="StandingOrder", extends=order.uuid, slots=[]))
    finding = next(f for f in run_check(model).findings if f.code == "MOD404")
    names = {i.uuid: getattr(i, "name", "") for i in model.index().values()}
    message = render(definition("MOD404").template, finding.args, names)
    assert "StandingOrder" in message, "the extending entity is not named"
    assert "flat table" in message, "it does not say why"


def test_an_abstract_descendant_does_not_raise_it(model) -> None:
    """An abstract entity is no table, so nothing is unreachable."""
    from dataclasses import replace
    from uuid import uuid4

    from designer_model import check as run_check

    order = next(e for e in model.entities if e.name == "Order")
    model.entities.append(replace(order, uuid=uuid4(), name="OrderKind", extends=order.uuid, abstract=True, slots=[]))
    assert not [f for f in run_check(model).findings if f.code == "MOD404"]


def test_a_leaf_target_is_not_warned_about(model) -> None:
    from designer_model import check as run_check

    assert not [f for f in run_check(model).findings if f.code == "MOD404"]
