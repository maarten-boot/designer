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


# --- MOD108: an argument the binding does not set ----------------------------


def mod108(model) -> list[str]:
    return [str(f.args["parameters"]) for f in check(model).findings if f.code == "MOD108"]


def test_a_type_binding_without_its_argument_is_incomplete(model) -> None:
    item = by_name(model.types, "CountryCode")
    item.validators.append(Binding(uuid=uuid4(), validator=builtin_id("max_length")))
    assert mod108(model) == ["max"]
    assert definition("MOD108").severity is Severity.INCOMPLETE
    assert blocks_export("MOD108")


def test_a_composite_needs_what_its_leaves_need(model) -> None:
    from designer_model.model import Validator

    leaf = by_name(model.validators, "is_order_number")
    composite = Validator(
        uuid=uuid4(),
        name="short_order_number",
        description="",
        created=leaf.created,
        modified=leaf.modified,
        context=leaf.context,
        kind="composite",
        expression=f"{leaf.uuid} AND {builtin_id('max_length')}",
    )
    model.validators.append(composite)
    by_name(model.types, "OrderNumber").validators.append(Binding(uuid=uuid4(), validator=composite.uuid))
    assert mod108(model) == ["max"]


def test_an_entity_binding_must_say_which_value(model) -> None:
    from designer_model.literals import ScalarLiteral
    from designer_model.model import LiteralArg

    entity = by_name(model.entities, "OrderLine")
    entity.validators.append(
        Binding(
            uuid=uuid4(),
            validator=builtin_id("min_value"),
            arguments={"min": LiteralArg(ScalarLiteral("integer", 1))},
        )
    )
    assert mod108(model) == ["value"]


def test_the_message_names_the_binding_and_what_is_missing(model) -> None:
    by_name(model.types, "CountryCode").validators.append(Binding(uuid=uuid4(), validator=builtin_id("max_length")))
    finding = next(f for f in check(model).findings if f.code == "MOD108")
    names = {i.uuid: i.name for i in model.index().values()} | {builtin_id("max_length"): "max_length"}
    message = render(definition("MOD108").template, finding.args, names)
    assert message.startswith("CountryCode (")
    assert "binds max_length (" in message
    assert message.endswith("without setting max")


# --- a composite naming something that does not exist ------------------------


def test_an_unresolved_name_in_a_composite_is_reported(model) -> None:
    from designer_model.diagnostics import TextSpan

    composite = by_name(model.validators, "order_reference")
    composite.expression = f"{composite.expression} AND nosuch"
    findings = [f for f in check(model).findings if f.code == "MOD113"]
    assert [f.args["target"] for f in findings] == ["nosuch"]
    start = composite.expression.index("nosuch")
    assert findings[0].span == TextSpan(start, start + len("nosuch"))


def test_stored_uuids_are_not_mistaken_for_names(model) -> None:
    # order_reference holds two UUIDs, one of whose segments begins with a letter
    assert not [f for f in check(model).findings if f.code == "MOD113"]


# --- naming: contexts and interfaces ------------------------------------------


def _context(model, name, parent):
    from designer_model.model import Context

    c = Context(
        uuid=uuid4(),
        name=name,
        description="",
        created=model.contexts[0].created,
        modified=model.contexts[0].modified,
        parent=parent,
    )
    model.contexts.append(c)
    return c


def test_context_names_are_unique_among_siblings_only(model) -> None:
    sales, support = by_name(model.contexts, "sales"), by_name(model.contexts, "support")
    _context(model, "archive", sales.uuid)
    _context(model, "archive", support.uuid)
    assert "MOD301" not in check(model).codes
    _context(model, "archive", sales.uuid)
    assert check(model).codes.count("MOD301") == 1


def test_an_interface_is_held_to_the_naming_rules(model) -> None:
    import datetime as dt

    from designer_model.model import Interface

    now = dt.datetime(2026, 10, 17, tzinfo=dt.UTC)
    for name in ("bad name!", "bad name!", ""):
        model.interfaces.append(
            Interface(
                uuid=uuid4(),
                name=name,
                description="",
                created=now,
                modified=now,
                context=model.contexts[0].uuid,
                base_type="string",
                picture="X(3)",
            )
        )
    codes = check(model).codes
    assert "MOD303" in codes and "MOD301" in codes and "MOD106" in codes


# --- overrides over a base type -----------------------------------------------


def test_overriding_a_base_typed_slot_with_another_base_widens(model) -> None:
    """`quantity` is a plain integer on OrderLine; an override built on string
    is not a narrowing of it, though neither side is a named Type."""
    from dataclasses import replace

    line = by_name(model.entities, "OrderLine")
    child = replace(line, uuid=uuid4(), name="BulkLine", abstract=False, extends=line.uuid, slots=[], validators=[])
    quantity = next(s for s in line.slots if s.slot_name == "quantity")
    short = by_name(model.types, "ShortText")
    child.slots = [replace(quantity, uuid=uuid4(), type_override=short.uuid, default=None)]
    model.entities.append(child)
    (finding,) = [f for f in check(model).findings if f.code == "MOD413"]
    assert finding.args["inherited"] == "integer"


def test_a_type_over_the_same_base_narrows_it(model) -> None:
    from dataclasses import replace

    from designer_model.model import BaseTypeRef, Type

    line = by_name(model.entities, "OrderLine")
    money = by_name(model.types, "Money")
    counted = Type(
        uuid=uuid4(),
        name="Count",
        description="",
        created=money.created,
        modified=money.modified,
        context=money.context,
        parent=BaseTypeRef("integer"),
    )
    model.types.append(counted)
    child = replace(line, uuid=uuid4(), name="BulkLine", abstract=False, extends=line.uuid, slots=[], validators=[])
    quantity = next(s for s in line.slots if s.slot_name == "quantity")
    child.slots = [replace(quantity, uuid=uuid4(), type_override=counted.uuid)]
    model.entities.append(child)
    assert "MOD413" not in check(model).codes


# --- the mutation table in the example notes §5 ------------------------------


def _mutate_override(m):
    slot = next(s for s in by_name(m.entities, "OrderLine").slots if s.slot_name == "line_total")
    slot.type_override = by_name(m.types, "ShortText").uuid


def _mutate_required(m):
    next(s for s in by_name(m.entities, "LineItem").slots if s.slot_name == "line_total").required = True
    next(s for s in by_name(m.entities, "OrderLine").slots if s.slot_name == "line_total").required = False


def _mutate_closure(m):
    schema = by_name(m.schemas, "sales_schema")
    schema.members = tuple(u for u in schema.members if u != by_name(m.entities, "Customer").uuid)


def _mutate_target(m):
    slot = next(s for s in by_name(m.entities, "OrderLine").slots if s.slot_name == "order")
    slot.target = by_name(m.entities, "LineItem").uuid


def _mutate_path(m):
    binding = by_name(m.schemas, "sales_schema").validators[0]
    order, ship = binding.arguments["value"].path
    binding.arguments["value"] = PathArg((order, ship, ship))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_mutate_override, {"MOD413"}),
        (_mutate_required, {"MOD412"}),
        (_mutate_closure, {"MOD503", "MOD509"}),
        (_mutate_target, {"MOD401", "MOD404", "MOD503", "MOD506", "MOD509"}),
        (_mutate_path, {"MOD508"}),
    ],
)
def test_the_example_notes_mutations_produce_what_they_say(model, mutate, expected) -> None:
    mutate(model)
    assert new_codes(model) == expected


# --- the checks added on 19 October -----------------------------------------------


def _findings(model, code):
    return [f for f in check(model).findings if f.code == code]


def test_a_misspelled_base_type_is_reported(model) -> None:
    from designer_model.model import BaseTypeRef

    by_name(model.types, "ShortText").parent = BaseTypeRef("strng")
    by_name(model.properties, "quantity").type = BaseTypeRef("integr")
    found = _findings(model, "MOD114")
    assert sorted(f.args["name"] for f in found) == ["integr", "strng"]
    assert "integer" in found[0].args["known"]


def test_a_default_of_the_wrong_base_type_is_refused(model) -> None:
    from designer_model.literals import ScalarLiteral

    quantity = next(s for s in by_name(model.entities, "OrderLine").slots if s.slot_name == "quantity")
    quantity.default = ScalarLiteral("string", "one")
    (finding,) = _findings(model, "MOD415")
    assert finding.args["reason"] == "is a string, but the slot holds integer"


def test_a_default_the_type_refuses_is_reported_with_the_rule(model) -> None:
    from decimal import Decimal

    from designer_model.literals import ScalarLiteral

    line_total = next(s for s in by_name(model.entities, "OrderLine").slots if s.slot_name == "line_total")
    line_total.default = ScalarLiteral("decimal", Decimal("0.00"))  # PositiveMoney: positive
    (finding,) = _findings(model, "MOD415")
    assert finding.args["reason"] == "the slot's type refuses (positive)"


def test_a_default_the_type_admits_says_nothing(model) -> None:
    # Order.total defaults to 0.00 on Money, which allows zero
    assert _findings(model, "MOD415") == []


def test_a_default_is_not_blamed_for_a_rule_that_cannot_answer(model) -> None:
    from decimal import Decimal

    from designer_model.literals import ScalarLiteral

    money = by_name(model.types, "Money")
    money.validators.append(Binding(uuid=uuid4(), validator=builtin_id("max_value")))  # no `max`: MOD108
    total = next(s for s in by_name(model.entities, "Order").slots if s.slot_name == "total")
    total.default = ScalarLiteral("decimal", Decimal("1.00"))
    assert _findings(model, "MOD415") == []
    assert _findings(model, "MOD108")


def test_an_override_may_not_retarget_a_reference(model) -> None:
    from dataclasses import replace

    line = by_name(model.entities, "OrderLine")
    child = replace(line, uuid=uuid4(), name="ReturnLine", abstract=False, extends=line.uuid, slots=[], validators=[])
    order = next(s for s in line.slots if s.slot_name == "order")
    child.slots = [replace(order, uuid=uuid4(), target=by_name(model.entities, "Customer").uuid)]
    model.entities.append(child)
    (finding,) = _findings(model, "MOD416")
    assert finding.args["inherited"] == ItemRef(by_name(model.entities, "Order").uuid)


def _authored(model, name, expression, kind="leaf", parameters=()):
    from designer_model.model import Validator

    v = Validator(
        uuid=uuid4(),
        name=name,
        description="",
        created=model.validators[0].created,
        modified=model.validators[0].modified,
        context=model.contexts[0].uuid,
        kind=kind,
        parameters=tuple(parameters),
        expression=expression,
    )
    model.validators.append(v)
    return v


def test_a_broken_validator_is_reported_though_nothing_uses_it(model) -> None:
    broken = _authored(model, "broken", "len(value) <=")
    (finding,) = _findings(model, "EXP112")
    assert finding.subject.item_uuid == broken.uuid
    assert str(finding.subject).endswith(".expression")


def test_a_broken_validator_is_reported_once_however_many_use_it(model) -> None:
    unused = _authored(model, "too_many", "len(value) > 0", parameters=("spare",))
    for type_name in ("ShortText", "CountryCode"):
        by_name(model.types, type_name).validators.append(Binding(uuid=uuid4(), validator=unused.uuid))
    found = _findings(model, "EXP404")
    assert len(found) == 1 and found[0].subject.item_uuid == unused.uuid


def test_a_composite_that_does_not_parse_is_reported(model) -> None:
    leaf = by_name(model.validators, "is_order_number")
    _authored(model, "dangling", f"{leaf.uuid} AND", kind="composite")
    assert len(_findings(model, "EXP112")) == 1


def test_an_unfinished_validator_says_nothing_yet(model) -> None:
    _authored(model, "later", "")
    assert not [f for f in check(model).findings if f.code.startswith("EXP")]


# --- fix hints (appendix diagnostics §7) -------------------------------------------


def test_a_path_leaving_the_schema_offers_to_add_the_entity(model) -> None:
    schema = by_name(model.schemas, "sales_schema")
    customer = by_name(model.entities, "Customer")
    schema.members = tuple(m for m in schema.members if m != customer.uuid)
    (finding,) = _findings(model, "MOD509")
    assert finding.fix.action == "add_schema_member"
    assert finding.fix.args == {"schema": str(schema.uuid), "entity": str(customer.uuid)}
    assert finding.fix.label == "Add Customer to the schema"


def test_a_widening_override_offers_a_narrowing_type_when_there_is_one(model) -> None:
    slot = next(s for s in by_name(model.entities, "OrderLine").slots if s.slot_name == "line_total")
    slot.type_override = by_name(model.types, "ShortText").uuid  # inherits Money; PositiveMoney narrows it
    (finding,) = _findings(model, "MOD413")
    assert finding.fix.action == "choose_narrowing_type"
    assert finding.fix.label == "Choose a Type that narrows Money"


def test_no_hint_when_nothing_narrows(model) -> None:
    from dataclasses import replace

    line = by_name(model.entities, "OrderLine")
    child = replace(line, uuid=uuid4(), name="BulkLine", abstract=False, extends=line.uuid, slots=[], validators=[])
    quantity = next(s for s in line.slots if s.slot_name == "quantity")  # a plain integer: no Type narrows it
    child.slots = [replace(quantity, uuid=uuid4(), type_override=by_name(model.types, "ShortText").uuid, default=None)]
    model.entities.append(child)
    (finding,) = _findings(model, "MOD413")
    assert finding.fix is None


# --- argument kinds and patterns (second crosscheck) ---------------------------------


def test_a_rule_given_the_wrong_kind_of_argument_is_refused(model) -> None:
    from designer_model.literals import ScalarLiteral
    from designer_model.model import LiteralArg

    any_slot = by_name(model.entities, "Customer").slots[0].uuid
    by_name(model.types, "ShortText").validators.append(
        Binding(uuid=uuid4(), validator=builtin_id("max_length"), arguments={"max": SlotArg(any_slot)})
    )
    sales = by_name(model.schemas, "sales_schema")
    sales.validators[0].arguments["value"] = PathArg(())
    found = sorted((f.args["got"], f.args["site"]) for f in _findings(model, "MOD417"))
    assert found == [("a slot", "a Type"), ("an empty path", "a Schema")]
    _ = ScalarLiteral, LiteralArg  # the literal kind is accepted everywhere


def test_a_pattern_argument_that_does_not_compile_is_reported(model) -> None:
    from designer_model.literals import ScalarLiteral
    from designer_model.model import LiteralArg

    by_name(model.types, "ShortText").validators.append(
        Binding(
            uuid=uuid4(),
            validator=builtin_id("matches"),
            arguments={"pattern": LiteralArg(ScalarLiteral("string", "[a-"))},
        )
    )
    (finding,) = _findings(model, "EXP305")
    assert "pattern" in finding.args["message"]
