"""Schema export (spec §9.6).

The acceptance test is the first one: `examples/sales_schema.export.json` was
written by hand and agreed before the exporter existed, and the exporter must
reproduce it byte for byte. The rest pin the rules that sample cannot show.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from decimal import Decimal
from uuid import uuid4

import pytest

from designer_model import load
from designer_model.export import ExportError, _source, _substitute, dumps, export_schema
from designer_model.ids import builtin_id
from designer_model.literals import ListLiteral, ScalarLiteral
from designer_model.model import Binding, Interface, InterfaceBinding, LiteralArg, TypeRef, Validator

EXAMPLES = pathlib.Path(__file__).resolve().parents[3] / "examples"
EXAMPLE = EXAMPLES / "sales.json"
SAMPLE = EXAMPLES / "sales_schema.export.json"
NOW = dt.datetime(2026, 10, 17, tzinfo=dt.UTC)


@pytest.fixture
def model():
    return load(EXAMPLE)


def named(items, name):
    """By name, from the model's items or from the exported document's."""
    return next(i for i in items if (i["name"] if isinstance(i, dict) else i.name) == name)


def export(model, schema="sales_schema"):
    return export_schema(model, named(model.schemas, schema).uuid)


def table(document, name):
    return named(document["tables"], name)


def column(document, table_name, column_name):
    return named(table(document, table_name)["columns"], column_name)


def add_validator(model, name, kind, expression, context="sales"):
    v = Validator(
        uuid=uuid4(),
        name=name,
        description="",
        created=NOW,
        modified=NOW,
        context=named(model.contexts, context).uuid,
        kind=kind,
        expression=expression,
        message=f"must be {name}",
    )
    model.validators.append(v)
    return v


# --- the agreed sample -------------------------------------------------------


def test_sales_schema_reproduces_the_agreed_sample(model):
    assert dumps(export(model)) == SAMPLE.read_text()


def test_the_same_model_exports_to_the_same_bytes(model):
    assert dumps(export(model)) == dumps(export(load(EXAMPLE)))


def test_every_member_schema_of_the_example_exports(model):
    for schema in model.schemas:
        assert export_schema(model, schema.uuid)["schema"]["name"] == schema.name


# --- gating ------------------------------------------------------------------


def test_an_unfinished_type_the_schema_does_not_use_does_not_block(model):
    # Weight has no parent (MOD101, which blocks), but nothing in sales_schema
    # uses it — the example's own export is the proof
    assert named(model.types, "Weight").parent is None
    export(model)


def test_an_unfinished_type_the_schema_uses_blocks(model):
    named(model.properties, "quantity").type = TypeRef(named(model.types, "Weight").uuid)
    with pytest.raises(ExportError) as raised:
        export(model)
    assert "MOD101" in [f.code for f in raised.value.blockers]


def test_an_unclosed_schema_blocks_although_it_is_a_warning(model):
    schema = named(model.schemas, "sales_schema")
    schema.members = tuple(m for m in schema.members if m != named(model.entities, "Customer").uuid)
    with pytest.raises(ExportError) as raised:
        export(model)
    assert "MOD503" in [f.code for f in raised.value.blockers]


def test_a_warning_is_carried_rather_than_blocking(model):
    warnings = export(model)["warnings"]
    assert [w["code"] for w in warnings] == ["MOD602"]
    assert warnings[0]["item"] == "Auditable"


def test_an_unknown_schema_is_refused(model):
    with pytest.raises(ExportError):
        export_schema(model, uuid4())


# --- columns -----------------------------------------------------------------


def test_a_reference_column_is_named_after_the_target_key(model):
    document = export(model)
    assert column(document, "Order", "customer_id")["relationship"] == "customer"
    assert column(document, "OrderLine", "order_order_number")["type"] == "OrderNumber"
    fk = table(document, "OrderLine")["foreign_keys"][0]
    assert fk["columns"] == ["order_order_number"]
    assert fk["target_columns"] == ["order_number"]


def test_an_index_declared_on_an_abstract_base_reaches_its_tables(model):
    from designer_model.model import Index, OrderTerm

    item = named(model.entities, "LineItem")  # abstract; OrderLine extends it
    line_total = next(s for s in item.slots if s.slot_name == "line_total")
    item.indexes = (Index((line_total.uuid,), unique=False),)
    item.default_order = (OrderTerm(line_total.uuid, ascending=False),)
    line = table(export(model), "OrderLine")
    assert line["indexes"] == [{"columns": ["line_total"], "unique": False}]
    assert line["default_order"] == [{"column": "line_total", "ascending": False}]


def test_an_inherited_rule_on_an_overridden_slot_names_the_override(model):
    from designer_model.ids import builtin_id
    from designer_model.literals import ScalarLiteral
    from designer_model.model import LiteralArg, SlotArg

    item = named(model.entities, "LineItem")  # OrderLine overrides line_total
    line_total = next(s for s in item.slots if s.slot_name == "line_total")
    item.validators.append(
        Binding(
            uuid=uuid4(),
            validator=builtin_id("max_value"),
            arguments={"value": SlotArg(line_total.uuid), "max": LiteralArg(ScalarLiteral("decimal", Decimal("1000")))},
        )
    )
    rules = [r for r in table(export(model), "OrderLine")["check"] if r["rule"] == "max_value"]
    assert [r["expression"] for r in rules] == ["line_total <= 1000"]


def test_tables_come_after_the_tables_they_reference(model):
    assert [t["name"] for t in export(model)["tables"]] == ["Customer", "Order", "OrderLine"]


def test_inherited_rules_come_before_the_types_own(model):
    rules = column(export(model), "OrderLine", "line_total")["check"]
    assert [(r["rule"], r["from"]) for r in rules] == [("non_negative", "Money"), ("positive", "PositiveMoney")]


def test_precision_and_scale_become_numeric_and_are_not_repeated(model):
    total = column(export(model), "Order", "total")
    assert total["numeric"] == {"precision": 12, "scale": 2}
    assert {r["rule"] for r in total["check"]} == {"non_negative"}


def test_max_length_adds_a_length_hint_and_stays_a_rule(model):
    name = column(export(model), "Customer", "name")
    assert name["length"] == 80
    assert "max_length" in [r["rule"] for r in name["check"]]


def add_interface(model, name, base, picture, **kwargs):
    face = Interface(
        uuid=uuid4(),
        name=name,
        description="",
        created=NOW,
        modified=NOW,
        context=model.contexts[0].uuid,
        base_type=base,
        picture=picture,
        **kwargs,
    )
    model.interfaces.append(face)
    return face


def test_a_numeric_interface_carries_its_separators(model):
    face = add_interface(model, "money_nl", "decimal", "#,##0.00", decimal_point=",", group_mark=".")
    named(model.types, "Money").interfaces.append(InterfaceBinding(uuid=uuid4(), interface=face.uuid))
    document = export(model)
    # inherited along the Type chain: PositiveMoney exports as though declared
    for table_name, column_name in (("Order", "total"), ("OrderLine", "line_total")):
        assert column(document, table_name, column_name)["interface"] == {
            "name": "money_nl",
            "picture": "#,##0.00",
            "decimal_point": ",",
            "group_mark": ".",
            "parse_lenient": True,
            "blank": "",
        }


def test_canonical_separators_are_still_written(model):
    face = add_interface(model, "money", "decimal", "#,##0.00")
    named(model.types, "Money").interfaces.append(InterfaceBinding(uuid=uuid4(), interface=face.uuid))
    block = column(export(model), "Order", "total")["interface"]
    assert (block["decimal_point"], block["group_mark"]) == (".", ",")


def test_a_non_numeric_interface_has_no_separators(model):
    face = add_interface(model, "code", "string", "X(2)U", blank="\u2014")
    named(model.types, "CountryCode").interfaces.append(InterfaceBinding(uuid=uuid4(), interface=face.uuid))
    assert column(export(model), "Customer", "country_code")["interface"] == {
        "name": "code",
        "picture": "X(2)U",
        "parse_lenient": True,
        "blank": "\u2014",
    }


def test_a_column_without_an_interface_says_so(model):
    assert column(export(model), "Customer", "name")["interface"] is None


# --- rules -------------------------------------------------------------------


def test_a_composite_expands_with_every_operand_bracketed(model):
    a = add_validator(model, "has_prefix", "leaf", 'starts_with(value, "ORD-")')
    b = add_validator(model, "is_long", "leaf", "len(value) > 9")
    c = add_validator(model, "is_short", "leaf", "len(value) < 40")
    combined = add_validator(model, "odd_rule", "composite", f"NOT {a.uuid} XOR ({b.uuid} AND {c.uuid})")
    order_number = named(model.types, "OrderNumber")
    order_number.validators = [Binding(uuid=uuid4(), validator=combined.uuid)]
    rule = column(export(model), "Order", "order_number")["check"][0]
    assert rule["expression"] == '(not (starts_with(value, "ORD-"))) != ((len(value) > 9) and (len(value) < 40))'


def test_a_rule_reading_the_clock_goes_to_the_application(model):
    not_today = add_validator(model, "not_today", "leaf", "value != str(today())", context="common")
    named(model.types, "ShortText").validators.append(Binding(uuid=uuid4(), validator=not_today.uuid))
    name = column(export(model), "Customer", "name")
    assert [r["rule"] for r in name["application"]] == ["not_today"]
    assert name["application"][0]["reason"] == "not deterministic"


def test_an_entity_rule_names_its_columns(model):
    rule = table(export(model), "OrderLine")["check"][0]
    assert rule["expression"] == "quantity >= 1"
    assert rule["arguments"] == {"min": {"integer": 1}}
    assert rule["message"] == "must be at least 1"


def test_a_schema_rule_walks_relationships(model):
    (rule,) = export(model)["application"]
    assert rule["anchor"] == "OrderLine"
    assert rule["paths"] == {"value": "order.ship_to_country", "other": "order.customer.country_code"}
    assert rule["expression"] == "order.ship_to_country == order.customer.country_code"


def test_a_list_argument_is_substituted_and_listed_in_the_message(model):
    priority = column(export(model, "support_schema"), "Ticket", "priority")
    (rule,) = priority["check"]
    assert rule["expression"] == 'value in ["low", "normal", "high", "urgent"]'
    assert rule["message"] == "must be one of low, normal, high, urgent"


def test_a_binding_message_override_wins(model):
    rules = column(export(model), "Customer", "name")["check"]
    assert named_rule(rules, "max_length")["message"] == "must be 80 characters or fewer"


def named_rule(rules, name):
    return next(r for r in rules if r["rule"] == name)


# --- substitution ------------------------------------------------------------


def test_substitution_leaves_strings_and_calls_alone():
    assert _substitute('len(value) <= len and "len" != len(value)', {"len": "5"}) == (
        'len(value) <= 5 and "len" != len(value)'
    )


def test_a_decimal_literal_stays_exact():
    assert _source(ScalarLiteral("decimal", Decimal("0.10"))) == "0.10"


def test_literal_sources():
    assert _source(ScalarLiteral("boolean", True)) == "True"
    assert _source(ScalarLiteral("string", 'say "hi"')) == '"say \\"hi\\""'
    assert _source(ListLiteral("integer", (1, 2))) == "[1, 2]"
    assert _source(ScalarLiteral("date", dt.date(2026, 1, 2))) == '"2026-01-02"'


def test_a_binding_with_an_unset_argument_blocks(model):
    # the expression would name a parameter nothing supplies (MOD108)
    binding = Binding(uuid=uuid4(), validator=builtin_id("max_length"), arguments={})
    named(model.types, "CountryCode").validators.append(binding)
    with pytest.raises(ExportError) as raised:
        export(model)
    assert [f.code for f in raised.value.blockers] == ["MOD108"]
    binding.arguments = {"max": LiteralArg(ScalarLiteral("integer", 2))}
    rules = column(export(model), "Customer", "country_code")["check"]
    assert named_rule(rules, "max_length")["expression"] == "len(value) <= 2"


# --- the other example files --------------------------------------------------

INTERFACES = EXAMPLES / "sales_interfaces.json"


def test_support_schema_reproduces_its_example(model):
    assert dumps(export(model, "support_schema")) == (EXAMPLES / "support_schema.export.json").read_text()


def test_the_interfaces_example_reproduces_its_export():
    m = load(INTERFACES)
    exported = dumps(export_schema(m, named(m.schemas, "sales_schema").uuid))
    assert exported == (EXAMPLES / "sales_interfaces.export.json").read_text()


def test_a_string_mentioning_the_clock_is_not_a_clock_rule(model):
    """Determinism is found on the syntax tree: `"now()"` in a string is text,
    so the rule is a database check and the model check says nothing."""
    from designer_model import check

    literal = add_validator(model, "not_the_word", "leaf", 'value != "now()"', context="common")
    named(model.types, "ShortText").validators.append(Binding(uuid=uuid4(), validator=literal.uuid))
    assert check(model).codes.count("MOD602") == 1  # Auditable's in_past, as before
    name = column(export(model), "Customer", "name")
    assert "not_the_word" in [r["rule"] for r in name["check"]]


def test_the_broken_example_is_blocked_by_what_it_is_built_to_show():
    """examples/sales_broken.json: Customer missing from sales_schema, and a
    widening override — the export is refused, and every blocker offers a fix."""
    from designer_model import check

    m = load(EXAMPLES / "sales_broken.json")
    with pytest.raises(ExportError) as raised:
        export_schema(m, named(m.schemas, "sales_schema").uuid)
    blockers = sorted(raised.value.blockers, key=lambda f: f.code)
    assert [f.code for f in blockers] == ["MOD413", "MOD503", "MOD509"]
    assert all(f.fix is not None for f in blockers)
    export_schema(m, named(m.schemas, "support_schema").uuid)  # untouched, still exports
    assert sorted(check(m).codes) == ["MOD101", "MOD413", "MOD503", "MOD509", "MOD601", "MOD601", "MOD602"]


def test_a_composite_without_a_message_says_what_its_operands_say(model):
    """Spec §5.5: no message of its own, so the export builds one — all of an
    AND, any of an OR — from the operands' own."""
    reference = named(model.validators, "order_reference")  # is_order_number OR is_uuid
    reference.message = ""
    rule = column(export(model), "Order", "order_number")["check"][0]
    assert rule["message"] == "must look like ORD-000123, or must be a UUID"
