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


def test_a_type_with_an_interface_carries_its_presentation(model):
    face = Interface(
        uuid=uuid4(),
        name="money_nl",
        description="",
        created=NOW,
        modified=NOW,
        context=model.contexts[0].uuid,
        base_type="decimal",
        picture="#,##0.00",
        decimal_point=",",
        group_mark=".",
    )
    model.interfaces.append(face)
    named(model.types, "Money").interfaces.append(InterfaceBinding(uuid=uuid4(), interface=face.uuid))
    document = export(model)
    # inherited along the Type chain: PositiveMoney presents as Money does
    for table_name, column_name in (("Order", "total"), ("OrderLine", "line_total")):
        presentation = column(document, table_name, column_name)["presentation"]
        assert presentation["interface"] == "money_nl"
        assert (presentation["decimal_point"], presentation["group_mark"]) == (",", ".")


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
