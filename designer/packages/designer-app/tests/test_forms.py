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
    """Inherited slots are shown so the effective record reads in one place,
    marked so it is clear they are edited elsewhere."""
    field = spec_for(model, library, "Order").by_key("slots")
    assert field.kind == "table"
    rows = {row.cells[0]: row for row in field.rows}
    assert "inherited" in rows["created_at"].tags
    assert not rows["created_at"].removable
    assert rows["order_number"].tags == ()
    assert rows["order_number"].removable


def test_the_slot_table_offers_the_actions_that_apply(model, library) -> None:
    field = spec_for(model, library, "Order").by_key("slots")
    by_name = {a.name: a for a in field.actions}
    assert by_name["add_value_slot"].requires == ""
    assert by_name["remove_slot"].requires == "own"
    assert by_name["override_slot"].requires == "inherited"


def test_the_slot_table_shows_the_type_or_the_target(model, library) -> None:
    rows = {r.cells[0]: r.cells for r in spec_for(model, library, "Order").by_key("slots").rows}
    assert rows["total"][2] == "Money"
    assert rows["customer"][2] == "\u2192 Customer"


def test_a_narrowed_slot_shows_the_narrowed_type(model, library) -> None:
    rows = {r.cells[0]: r.cells for r in spec_for(model, library, "OrderLine").by_key("slots").rows}
    assert rows["line_total"][2] == "PositiveMoney"


def test_slots_are_listed_in_their_stored_order(model, library) -> None:
    """Order is stored, so the table has to honour it rather than sort."""
    field = spec_for(model, library, "Order").by_key("slots")
    positions = [r.cells[0] for r in field.rows]
    assert positions.index("order_number") < positions.index("total")


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


def test_a_type_lists_its_rules_in_a_table(model, library) -> None:
    field = spec_for(model, library, "Money").by_key("validators")
    assert field.kind == "table"
    assert field.columns == ("Rule", "Arguments")
    rules = {row.cells[0]: row.cells[1] for row in field.rows}
    assert "non_negative" in rules
    assert rules["max_scale"] == "s=2"


def test_an_entity_rule_names_the_slot_it_applies_to(model, library) -> None:
    """A Type's rules apply to the type itself, so that column is only there
    where it means something."""
    field = spec_for(model, library, "Auditable").by_key("validators")
    assert field.columns == ("Rule", "Applies to", "Arguments")
    assert field.rows[0].cells[:2] == ("in_past", "created_at")


def test_the_rules_table_offers_add_edit_and_remove(model, library) -> None:
    field = spec_for(model, library, "Money").by_key("validators")
    assert [a.name for a in field.actions] == ["add_rule", "edit_rule", "remove_rule"]
    assert all(a.needs_row for a in field.actions if a.name != "add_rule")


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


# --- copies of built-ins -----------------------------------------------------


def copy_of_builtin(model, library, name, context_name="common"):
    from designer_app import factory

    context = next(c for c in model.contexts if c.name == context_name)
    copy = factory.duplicate(library.by_name(name))
    copy.name, copy.context = name, context.uuid
    model.validators.append(copy)
    return copy


def test_a_copy_says_it_takes_precedence(model, library) -> None:
    """The point of copying is that the name now means yours — which is not a
    fault, and is worth seeing without hunting for it."""
    copy = copy_of_builtin(model, library, "is_uuid")
    field = forms.describe(model, copy.uuid, library, copy.context).by_key("overrides")
    assert field is not None
    assert field.value == "the built-in is_uuid"
    assert field.emphasis == "attention"


def test_the_note_says_the_built_in_is_unchanged(model, library) -> None:
    """Every rule already bound to it still uses it."""
    copy = copy_of_builtin(model, library, "is_uuid")
    field = forms.describe(model, copy.uuid, library, copy.context).by_key("overrides")
    assert "still uses it" in field.note


def test_a_validator_of_its_own_name_says_nothing_of_the_sort(model, library) -> None:
    assert spec_for(model, library, "is_order_number").by_key("overrides") is None


def test_the_built_in_says_where_it_was_taken_over(model, library) -> None:
    copy_of_builtin(model, library, "is_uuid")
    field = forms.describe(model, library.by_name("is_uuid").uuid, library).by_key("shadowed")
    assert field is not None
    assert field.value == ["is_uuid in common"]
    assert field.emphasis == "attention"


def test_an_untouched_built_in_says_nothing(model, library) -> None:
    assert forms.describe(model, library.by_name("max_length").uuid, library).by_key("shadowed") is None


def test_shadowing_is_reported_as_soon_as_the_name_is_set(model, library) -> None:
    """It compares a name against the standard library, which does not change,
    so it does not need a whole-model pass."""
    from designer_model import Checker
    from designer_model.diagnostics import Scope

    copy = copy_of_builtin(model, library, "is_uuid")
    incremental = Checker(model, library).run(frozenset({Scope.ITEM, Scope.CONTEXT}))
    found = [f for f in incremental.findings if f.code == "MOD304"]
    assert found and found[0].subject.item_uuid == copy.uuid


def test_every_label_in_the_form_carries_a_style() -> None:
    """The form sits on a near-white panel; a label without a style keeps the
    theme's grey and sits on it like a patch.

    Three labels lost theirs at once when a batch of edits stopped at a failure
    and the rest silently did not run — which no behavioural test would see.
    """
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_app" / "formview.py"
    tree = ast.parse(source.read_text())
    unstyled = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Label"
        and "style" not in {keyword.arg for keyword in node.keywords}
    ]
    assert unstyled == [], f"labels without a style at lines {unstyled}"


def test_schema_members_read_alphabetically(model, library) -> None:
    field = spec_for(model, library, "sales_schema").by_key("members")
    names = [row.cells[0] for row in field.rows]
    assert names == sorted(names, key=str.lower)


def test_slots_keep_their_stored_order(model, library) -> None:
    """Never alphabetical: the order of slots is stored, it is what the Up and
    Down buttons change, and it survives to the generated table."""
    field = spec_for(model, library, "Order").by_key("slots")
    names = [row.cells[0] for row in field.rows]
    assert names != sorted(names, key=str.lower)
    assert names.index("order_number") < names.index("customer")


# --- composite validators ----------------------------------------------------


def test_the_kind_can_be_chosen(model, library) -> None:
    """A new validator is a leaf; without this there is no way to make one
    composite, and no way to combine rules at all."""
    field = spec_for(model, library, "is_order_number").by_key("kind")
    assert field.editable
    assert {c.id for c in field.choices} == {"leaf", "composite"}


def test_a_composite_expression_survives_parentheses(model, library) -> None:
    from designer_model.expressions import tokens

    composite = by_name(model.validators, "order_reference")
    written = "is_order_number AND is_uuid OR (NOT is_email)"
    stored = tokens.to_stored(written, forms.resolver(model, library, composite.context))
    assert "is_order_number" not in stored, "a name was left in the stored form"
    assert tokens.to_display(stored, forms.validator_names(model, library, composite.context)).text == written


def test_the_expression_note_shows_the_syntax(model, library) -> None:
    """Nothing else in the interface says what a composite may contain."""
    note = spec_for(model, library, "order_reference").by_key("expression").note
    assert "AND" in note and "OR" in note and "NOT" in note
    assert "parentheses" in note


def test_a_validator_says_which_base_types_it_takes(model, library) -> None:
    """Derived from the expression, never declared: a field to pick one would
    either throw the polymorphism away or drift from the expression."""
    field = forms.describe(model, library.by_name("non_negative").uuid, library).by_key("accepts")
    assert field.value == "integer, real, decimal"
    assert not field.editable


def test_a_validator_taking_everything_says_so_briefly(model, library) -> None:
    field = forms.describe(model, library.by_name("equals").uuid, library).by_key("accepts")
    assert field.value == "any base type"


def test_an_authored_validator_says_it_too(model, library) -> None:
    own = by_name(model.validators, "is_order_number")
    assert forms.describe(model, own.uuid, library, own.context).by_key("accepts").value == "string"


# --- how a rule is used, versus how it is built -------------------------------


def test_a_rule_says_how_it_is_written_where_it_is_used(model, library) -> None:
    """`is_country_code` is *used* as `is_country_code`; its expression is a
    regex call, which is how it is built."""
    spec = forms.describe(model, library.by_name("is_country_code").uuid, library)
    assert spec.by_key("usage").value == "is_country_code"
    assert spec.by_key("expression").value.startswith("regex_full_match")


def test_usage_names_the_arguments_to_supply(model, library) -> None:
    spec = forms.describe(model, library.by_name("between").uuid, library)
    assert spec.by_key("usage").value == "between(min, max)"


def test_usage_differs_from_the_expression_even_when_they_look_alike(model, library) -> None:
    """`ends_with` is the case that makes showing only the expression
    misleading: it is a call to the function of the same name, so it reads like
    usage while carrying an extra `value` argument that is never written."""
    spec = forms.describe(model, library.by_name("ends_with").uuid, library)
    assert spec.by_key("usage").value == "ends_with(suffix)"
    assert spec.by_key("expression").value == "ends_with(value, suffix)"


def test_a_composite_takes_on_its_operands_parameters(model, library) -> None:
    spec = forms.describe(model, library.by_name("is_safe_identifier").uuid, library)
    assert spec.by_key("usage").value == "is_safe_identifier(max)"
    assert spec.by_key("expression").value == "is_identifier AND max_length"


def test_a_rule_that_exposes_a_function_says_which(model, library) -> None:
    """Useful for writing your own: the same function is available directly."""
    spec = forms.describe(model, library.by_name("matches").uuid, library)
    assert "regex_full_match" in spec.by_key("expression").note


def test_a_rule_built_from_operators_says_so_instead(model, library) -> None:
    spec = forms.describe(model, library.by_name("between").uuid, library)
    assert "a model for writing your own" in spec.by_key("expression").note


def test_an_authored_rule_shows_its_usage_too(model, library) -> None:
    own = by_name(model.validators, "is_order_number")
    assert forms.describe(model, own.uuid, library, own.context).by_key("usage").value == ("is_order_number")


def test_every_built_in_has_a_usage_line(model, library) -> None:
    for name in library.names:
        spec = forms.describe(model, library.by_name(name).uuid, library)
        assert spec.by_key("usage").value.startswith(name)
