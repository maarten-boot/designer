"""Form description and item creation.

Headless: which fields appear, which choices are offered, which would create a
cycle, where a finding attaches — all of it decidable without a display, and
none of it checkable by looking at a window.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import check, load
from designer_model.expressions import tokens
from designer_model.model import BaseTypeRef, TypeRef
from designer_model.stdlib import standard_library

from designer_app import factory, forms
from designer_app.rows import BASE_PREFIX

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


@pytest.fixture
def library():
    return standard_library()


def by_name(items, name):
    return next(i for i in items if i.name == name)


def spec_for(model, library, name, report=None):
    item = next(
        i
        for i in [
            *model.contexts,
            *model.validators,
            *model.types,
            *model.properties,
            *model.entities,
            *model.schemas,
        ]
        if i.name == name
    )
    return forms.describe(model, item.uuid, library, getattr(item, "context", None), report)


# --- the header -------------------------------------------------------------


HEADER = ["name", "description", "context_path", "uuid", "created", "modified"]


def test_every_kind_has_the_common_header(model, library) -> None:
    for name in ["common", "Money", "amount", "order_reference", "Order", "sales_schema"]:
        spec = spec_for(model, library, name)
        assert spec.keys()[: len(HEADER)] == HEADER


def test_every_form_says_where_the_item_lives(model, library) -> None:
    """Read-only: an item is moved by changing its context, not from here."""
    spec = spec_for(model, library, "order_reference")
    where = spec.by_key("context_path")
    assert where.value == "common \u203a sales"
    assert not where.editable


def test_a_context_shows_its_own_path(model, library) -> None:
    assert spec_for(model, library, "sales").by_key("context_path").value == "common \u203a sales"


def test_an_item_in_the_root_context_shows_just_that(model, library) -> None:
    assert spec_for(model, library, "Money").by_key("context_path").value == "common"


def test_identity_and_timestamps_are_not_editable(model, library) -> None:
    spec = spec_for(model, library, "Money")
    for key in ("uuid", "created", "modified"):
        assert not spec.by_key(key).editable


def test_an_unknown_uuid_describes_nothing(model, library) -> None:
    from uuid import uuid4

    assert forms.describe(model, uuid4(), library) is None


# --- choices ----------------------------------------------------------------


def test_a_type_may_narrow_a_base_type_or_another_type(model, library) -> None:
    spec = spec_for(model, library, "PositiveMoney")
    ids = {c.id for c in spec.by_key("parent").choices}
    assert f"{BASE_PREFIX}decimal" in ids
    assert str(by_name(model.types, "Money").uuid) in ids


def test_a_type_is_not_offered_its_own_descendants(model, library) -> None:
    """Offering them would let the user build a cycle and then be told off."""
    money = by_name(model.types, "Money")
    positive = by_name(model.types, "PositiveMoney")
    spec = spec_for(model, library, "Money")
    ids = {c.id for c in spec.by_key("parent").choices}
    assert str(positive.uuid) not in ids
    assert str(money.uuid) not in ids


def test_a_context_is_not_offered_its_own_subtree(model, library) -> None:
    common = by_name(model.contexts, "common")
    sales = by_name(model.contexts, "sales")
    ids = {c.id for c in forms.context_choices(model, exclude=common.uuid)}
    assert str(sales.uuid) not in ids
    assert str(common.uuid) not in ids


def test_an_entity_is_not_offered_its_own_descendants(model, library) -> None:
    line_item = by_name(model.entities, "LineItem")
    order_line = by_name(model.entities, "OrderLine")
    ids = {c.id for c in forms.entity_choices(model, line_item.context, exclude=line_item.uuid)}
    assert str(order_line.uuid) not in ids


def test_every_choice_list_offers_none(model, library) -> None:
    """An item is created empty, so unsetting has to be reachable."""
    for name, key in [("Money", "parent"), ("amount", "type"), ("Order", "extends")]:
        choices = spec_for(model, library, name).by_key(key).choices
        assert choices[0].id is None


def test_choices_respect_visibility(model, library) -> None:
    """A sibling context's types are not offered."""
    priority = by_name(model.types, "Priority")  # in support
    ids = {c.id for c in forms.type_choices(model, by_name(model.contexts, "sales").uuid)}
    assert str(priority.uuid) not in ids


def test_concrete_only_excludes_abstract_entities(model) -> None:
    abstract = by_name(model.entities, "Auditable")
    ids = {c.id for c in forms.entity_choices(model, None, concrete_only=True)}
    assert str(abstract.uuid) not in ids


# --- converting back --------------------------------------------------------


def test_a_base_type_choice_round_trips() -> None:
    assert forms.parse_type_ref(f"{BASE_PREFIX}string") == BaseTypeRef("string")


def test_a_type_choice_round_trips(model) -> None:
    money = by_name(model.types, "Money")
    assert forms.parse_type_ref(str(money.uuid)) == TypeRef(money.uuid)


def test_the_none_choice_clears_the_field() -> None:
    assert forms.parse_type_ref(None) is None
    assert forms.parse_item_ref(None) is None


# --- validators -------------------------------------------------------------


def test_a_composite_shows_operand_names_not_identities(model, library) -> None:
    """Renaming a validator cannot break an expression that uses it, which only
    works because the file holds identities and the screen holds names."""
    spec = spec_for(model, library, "order_reference")
    shown = spec.by_key("expression").value
    assert shown == "is_order_number OR is_uuid"
    assert "-" not in shown  # no uuids on screen


def test_a_composite_expression_round_trips(model, library) -> None:
    composite = by_name(model.validators, "order_reference")
    spec = spec_for(model, library, "order_reference")
    back = tokens.to_stored(spec.by_key("expression").value, forms.resolver(model, library, composite.context))
    assert back == composite.expression


def test_a_leaf_expression_is_shown_as_written(model, library) -> None:
    leaf = by_name(model.validators, "is_order_number")
    spec = spec_for(model, library, "is_order_number")
    assert spec.by_key("expression").value == leaf.expression
    assert spec.by_key("expression").converter == forms.PLAIN


def test_built_ins_can_be_named_in_an_expression(model, library) -> None:
    names = forms.validator_names(model, library, by_name(model.contexts, "sales").uuid)
    assert "max_length" in names.values()


# --- summaries --------------------------------------------------------------


def test_an_entity_lists_inherited_slots_and_says_so(model, library) -> None:
    spec = spec_for(model, library, "Order")
    lines = spec.by_key("slots").value
    assert any("created_at" in line and "inherited" in line for line in lines)
    assert any("order_number" in line and "inherited" not in line for line in lines)


def test_an_entity_lists_the_schemas_holding_it(model, library) -> None:
    """Editing this entity affects every schema listed, and that has to be
    visible before the edit, not after."""
    spec = spec_for(model, library, "Customer")
    assert set(spec.by_key("schemas").value) == {"sales_schema", "support_schema"}


def test_a_schema_reports_closure(model, library) -> None:
    assert spec_for(model, library, "sales_schema").by_key("closure").value == "closed"


def test_an_unclosed_schema_names_what_dangles(model, library) -> None:
    sales = by_name(model.schemas, "sales_schema")
    customer = by_name(model.entities, "Customer")
    sales.members = tuple(m for m in sales.members if m != customer.uuid)
    closure = spec_for(model, library, "sales_schema").by_key("closure").value
    assert "Order.customer" in closure


def test_a_type_summarises_its_rules(model, library) -> None:
    lines = spec_for(model, library, "Money").by_key("validators").value
    assert any("non_negative" in line for line in lines)


# --- findings ---------------------------------------------------------------


def test_a_finding_attaches_to_the_field_that_caused_it(model, library) -> None:
    report = check(model)
    spec = spec_for(model, library, "Weight", report)
    assert spec.by_key("parent").findings
    assert not spec.by_key("name").findings


def test_findings_elsewhere_do_not_leak_onto_this_item(model, library) -> None:
    report = check(model)
    spec = spec_for(model, library, "Money", report)
    assert all(not f.findings for f in spec.fields)


# --- creating ---------------------------------------------------------------


@pytest.mark.parametrize("kind", factory.KINDS)
def test_a_new_item_is_empty(kind, model) -> None:
    """Blank name, every reference unset: the rule the whole model rests on."""
    context = by_name(model.contexts, "sales").uuid
    created = factory.new_item(kind, context)
    assert created.name == ""
    assert created.description == ""
    if kind == "Context":
        assert created.parent == context
    else:
        assert created.context == context


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="no such kind"):
        factory.new_item("Nonsense")


def test_a_new_item_has_a_fresh_identity() -> None:
    assert factory.new_item("Type").uuid != factory.new_item("Type").uuid


def test_a_duplicate_keeps_everything_but_identity_and_name(model) -> None:
    money = by_name(model.types, "Money")
    copy = factory.duplicate(money)
    assert copy.uuid != money.uuid
    assert copy.name == ""
    assert copy.description == money.description
    assert copy.parent == money.parent
    assert len(copy.validators) == len(money.validators)


def test_a_duplicate_does_not_share_its_lists(model) -> None:
    """`replace` copies the reference, so without care an edit to the copy
    would reach the original."""
    money = by_name(model.types, "Money")
    copy = factory.duplicate(money)
    copy.validators.clear()
    assert money.validators


def test_duplicating_an_entity_copies_its_slots(model) -> None:
    order = by_name(model.entities, "Order")
    copy = factory.duplicate(order)
    assert len(copy.slots) == len(order.slots)
    copy.slots.clear()
    assert order.slots


# --- an edit belongs to the item it was typed into ---------------------------


def test_a_form_records_the_item_it_was_built_for(model, library) -> None:
    """An edit committed later must reach that item, not whatever is selected
    by the time the commit arrives."""
    money = by_name(model.types, "Money")
    spec = forms.describe(model, money.uuid, library, money.context)
    assert spec.uuid == money.uuid


def test_two_forms_do_not_share_an_identity(model, library) -> None:
    first = spec_for(model, library, "Money")
    second = spec_for(model, library, "amount")
    assert first.uuid != second.uuid


# --- the members table -------------------------------------------------------


def test_members_are_an_editable_table(model, library) -> None:
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert field.kind == "table"
    assert field.columns == ("Entity", "Context")
    assert {row.cells[0] for row in field.rows} == {"Customer", "Order", "OrderLine"}


def test_a_member_row_says_where_the_entity_lives(model, library) -> None:
    """Customer sits in a shared ancestor, which is what lets two schemas hold
    it — worth seeing in the row rather than having to go and look."""
    field = spec_for(model, library, "sales_schema").by_key("members")
    customer = next(row for row in field.rows if row.cells[0] == "Customer")
    assert customer.cells[1] == "common"


def test_the_table_offers_add_remove_and_close(model, library) -> None:
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert [a.name for a in field.actions] == ["add_member", "remove_member", "close_schema"]


def test_remove_needs_a_row_selected(model, library) -> None:
    field = spec_for(model, library, "sales_schema").by_key("members")
    remove = next(a for a in field.actions if a.name == "remove_member")
    assert remove.needs_row


def test_close_is_disabled_while_the_schema_is_closed(model, library) -> None:
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert not next(a for a in field.actions if a.name == "close_schema").enabled


def test_close_is_offered_once_something_dangles(model, library) -> None:
    sales = by_name(model.schemas, "sales_schema")
    customer = by_name(model.entities, "Customer")
    sales.members = tuple(m for m in sales.members if m != customer.uuid)
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert next(a for a in field.actions if a.name == "close_schema").enabled


def test_add_is_disabled_when_nothing_could_join(model, library) -> None:
    """Every visible concrete entity is already a member of support_schema."""
    field = spec_for(model, library, "support_schema").by_key("members")
    assert not next(a for a in field.actions if a.name == "add_member").enabled


def test_add_is_offered_when_something_could_join(model, library) -> None:
    sales = by_name(model.schemas, "sales_schema")
    sales.members = ()
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert next(a for a in field.actions if a.name == "add_member").enabled


def test_a_table_row_is_identified_by_the_entity(model, library) -> None:
    """Rows are addressed by identity, not position, so a reorder cannot make
    a button act on the wrong one."""
    sales = by_name(model.schemas, "sales_schema")
    field = spec_for(model, library, "sales_schema").by_key("members")
    assert {row.id for row in field.rows} == {str(m) for m in sales.members}


# --- built-in validators -----------------------------------------------------


def test_a_built_in_describes_itself(model, library) -> None:
    """Built-ins are global and never written to the model file, so looking one
    up in the model finds nothing. Reporting it as missing was wrong: it is
    there, it simply cannot be edited."""
    spec = forms.describe(model, library.by_name("max_length").uuid, library)
    assert spec is not None
    assert spec.title == "max_length"
    assert spec.read_only
    assert "cannot be edited" in spec.note


def test_every_field_of_a_built_in_is_read_only(model, library) -> None:
    spec = forms.describe(model, library.by_name("between").uuid, library)
    assert all(not f.editable for f in spec.fields)


def test_a_built_in_says_where_it_came_from(model, library) -> None:
    spec = forms.describe(model, library.by_name("max_length").uuid, library)
    assert spec.by_key("origin").value == "standard library"


def test_a_built_in_offers_to_be_copied(model, library) -> None:
    spec = forms.describe(model, library.by_name("max_length").uuid, library)
    assert [a.name for a in spec.actions] == ["fork_builtin"]


def test_a_built_in_reports_its_determinism(model, library) -> None:
    """A rule that reads the clock can never be a check constraint, and the
    form is where somebody would want to know that."""
    assert forms.describe(model, library.by_name("in_past").uuid, library).by_key("deterministic").value == "no"
    assert forms.describe(model, library.by_name("max_length").uuid, library).by_key("deterministic").value == "yes"


def test_a_built_in_composite_shows_operand_names(model, library) -> None:
    spec = forms.describe(model, library.by_name("non_blank").uuid, library)
    assert spec.by_key("expression").value == "non_empty AND trimmed"


def test_an_authored_form_is_not_read_only(model, library) -> None:
    assert not spec_for(model, library, "Money").read_only
    assert spec_for(model, library, "Money").actions == ()


def test_something_genuinely_absent_still_describes_nothing(model, library) -> None:
    from uuid import uuid4

    assert forms.describe(model, uuid4(), library) is None


# --- base types --------------------------------------------------------------


def test_a_base_type_describes_itself(model) -> None:
    """Selectable, and read-only. An item you can see and cannot inspect is
    worse than one you cannot see."""
    spec = forms.describe_base_type(model, "decimal")
    assert spec is not None
    assert spec.title == "decimal"
    assert spec.kind == "Base type"
    assert spec.read_only
    assert "cannot be edited" in spec.note


def test_every_base_type_has_a_form(model) -> None:
    from designer_model.expressions.types import BASE_TYPES

    for name in BASE_TYPES:
        assert forms.describe_base_type(model, name) is not None


def test_something_that_is_not_a_base_type_describes_nothing(model) -> None:
    assert forms.describe_base_type(model, "nonsense") is None


def test_a_base_type_lists_what_narrows_it(model) -> None:
    spec = forms.describe_base_type(model, "decimal")
    assert spec.by_key("built_on").value == ["Money"]
    assert spec.by_key("reaching").value == ["Money", "PositiveMoney"]


def test_a_base_type_nothing_uses_says_so(model) -> None:
    spec = forms.describe_base_type(model, "boolean")
    assert spec.by_key("built_on").value == ["none"]


def test_every_field_of_a_base_type_is_read_only(model) -> None:
    spec = forms.describe_base_type(model, "string")
    assert all(not f.editable for f in spec.fields if f.kind != "summary")
    assert spec.actions == ()


def test_a_base_type_identity_is_stable_but_never_stored(model) -> None:
    """A form needs something to be about; the document does not hold it."""
    assert forms.base_type_uuid("string") == forms.base_type_uuid("string")
    assert forms.base_type_uuid("string") != forms.base_type_uuid("integer")
    assert forms.base_type_uuid("string") not in model.index()
