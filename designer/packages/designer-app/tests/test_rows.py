"""Columns and linkage.

Headless on purpose: what goes in each column, in what order, under what
parent, is the part a display cannot help you verify — you would be reading
coloured rows and guessing.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import load
from designer_model.stdlib import standard_library

from designer_app import rows, selection

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


def by_name(items, name):
    return next(i for i in items if i.name == name)


def ctx(model, name):
    return by_name(model.contexts, name).uuid


# --- contexts ---------------------------------------------------------------


def test_context_tree_is_parented(model) -> None:
    data = rows.contexts(model)
    common = next(r for r in data.rows if r.label == "common")
    sales = next(r for r in data.rows if r.label == "sales")
    assert common.parent == ""
    assert sales.parent == common.id


def test_parents_come_before_children(model) -> None:
    """A tree widget inserts in one pass, so a child must never arrive first."""
    data = rows.entities(model, ctx(model, "sales"))
    seen: set[str] = set()
    for row in data.rows:
        assert row.parent == "" or row.parent in seen
        seen.add(row.id)


# --- visibility -------------------------------------------------------------


def test_a_context_shows_its_own_and_its_ancestors(model) -> None:
    labels = rows.entities(model, ctx(model, "sales")).labels()
    assert "Order" in labels  # sales
    assert "Customer" in labels  # common, an ancestor
    assert "Ticket" not in labels  # support, a sibling


def test_siblings_stay_hidden_from_each_other(model) -> None:
    labels = rows.entities(model, ctx(model, "support")).labels()
    assert "Ticket" in labels
    assert "Order" not in labels


# --- entities ---------------------------------------------------------------


def test_extension_tree_reflects_extends(model) -> None:
    data = rows.entities(model, ctx(model, "sales"))
    order_line = next(r for r in data.rows if r.label == "OrderLine")
    line_item = next(r for r in data.rows if r.label == "LineItem")
    assert order_line.parent == line_item.id


def test_abstract_entities_are_tagged(model) -> None:
    data = rows.entities(model, ctx(model, "sales"))
    assert "abstract" in next(r for r in data.rows if r.label == "LineItem").tags
    assert "abstract" not in next(r for r in data.rows if r.label == "Order").tags


def test_a_parent_outside_the_view_reparents_to_the_root(model) -> None:
    """Customer extends Auditable, which is visible from sales. Seen from a
    context where the parent is not, the child must still appear."""
    data = rows.entities(model, ctx(model, "support"))
    ticket = next(r for r in data.rows if r.label == "Ticket")
    assert ticket.parent in {"", *[r.id for r in data.rows]}


# --- types ------------------------------------------------------------------


def test_base_types_are_the_roots(model) -> None:
    data = rows.types(model, ctx(model, "common"))
    roots = [r for r in data.rows if r.parent == ""]
    assert {"string", "decimal", "integer"} <= {r.label for r in roots}
    assert all("builtin" in r.tags for r in roots if r.kind == "BaseType")


def test_a_type_hangs_under_its_base_type(model) -> None:
    data = rows.types(model, ctx(model, "common"))
    money = next(r for r in data.rows if r.label == "Money")
    assert money.parent == f"{rows.BASE_PREFIX}decimal"


def test_a_narrowing_type_hangs_under_the_type_it_narrows(model) -> None:
    data = rows.types(model, ctx(model, "common"))
    positive = next(r for r in data.rows if r.label == "PositiveMoney")
    money = next(r for r in data.rows if r.label == "Money")
    assert positive.parent == money.id


def test_an_incomplete_type_is_still_reachable(model) -> None:
    """Weight has no parent yet. It must sit at the root rather than vanish."""
    data = rows.types(model, ctx(model, "common"))
    weight = next(r for r in data.rows if r.label == "Weight")
    assert weight.parent == ""
    assert "incomplete" in weight.tags


# --- validators -------------------------------------------------------------


def test_built_ins_are_hidden_by_default(model) -> None:
    labels = rows.validators(model, ctx(model, "sales"), library=standard_library()).labels()
    assert "is_order_number" in labels
    assert "max_length" not in labels


def test_built_ins_can_be_shown_and_are_tagged(model) -> None:
    data = rows.validators(model, ctx(model, "sales"), library=standard_library(), show_builtins=True)
    max_length = next(r for r in data.rows if r.label == "max_length")
    assert "builtin" in max_length.tags
    assert len(data.rows) > 40


def test_authored_validators_sort_before_built_ins(model) -> None:
    data = rows.validators(model, ctx(model, "sales"), library=standard_library(), show_builtins=True)
    first_builtin = next(i for i, r in enumerate(data.rows) if "builtin" in r.tags)
    assert all("builtin" not in r.tags for r in data.rows[:first_builtin])


# --- filtering --------------------------------------------------------------


def test_filtering_a_flat_column(model) -> None:
    labels = rows.properties(model, ctx(model, "sales"), "count").labels()
    assert labels == ["country_code"] or "country_code" in labels


def test_filtering_a_tree_keeps_the_ancestors_of_a_match(model) -> None:
    """Hiding the parent would orphan the match."""
    data = rows.types(model, ctx(model, "common"), "PositiveMoney")
    labels = data.labels()
    assert "PositiveMoney" in labels
    assert "Money" in labels and "decimal" in labels


def test_ancestors_kept_only_for_context_are_tagged(model) -> None:
    data = rows.types(model, ctx(model, "common"), "PositiveMoney")
    money = next(r for r in data.rows if r.label == "Money")
    positive = next(r for r in data.rows if r.label == "PositiveMoney")
    assert "context-only" in money.tags
    assert "context-only" not in positive.tags


def test_a_filter_matching_nothing_empties_the_column(model) -> None:
    assert rows.properties(model, ctx(model, "sales"), "zzzz").rows == []


# --- unnamed items ----------------------------------------------------------


def test_a_blank_name_shows_a_placeholder(model) -> None:
    """A new item is created empty and has to be selectable before it is named."""
    by_name(model.types, "Weight").name = ""
    data = rows.types(model, ctx(model, "common"))
    placeholder = next(r for r in data.rows if r.label == "<unnamed Type>")
    assert "unnamed" in placeholder.tags


# --- linkage ----------------------------------------------------------------


def test_a_schema_highlights_its_members(model) -> None:
    """Not filters them. The Entity column is where members are chosen from, so
    hiding the non-members hides exactly what somebody adding one is looking
    for."""
    sales = by_name(model.schemas, "sales_schema")
    result = selection.focus(model, selection.Selection(schema=sales.uuid))
    assert result.contains == set(sales.members)
    labels = rows.entities(model, ctx(model, "sales")).labels()
    assert "Ticket" not in labels  # a sibling context, still invisible
    assert "Auditable" in labels  # not a member, and still shown


def test_a_member_is_tagged_as_contained(model) -> None:
    sales = by_name(model.schemas, "sales_schema")
    customer = by_name(model.entities, "Customer")
    result = selection.focus(model, selection.Selection(schema=sales.uuid))
    assert "contains" in selection.tags_for(customer.uuid, result)


def test_an_entity_highlights_its_properties_and_references(model) -> None:
    order = by_name(model.entities, "Order")
    customer = by_name(model.entities, "Customer")
    country = by_name(model.properties, "country_code")
    result = selection.focus(model, selection.Selection(entity=order.uuid))
    assert country.uuid in result.uses
    assert customer.uuid in result.references


def test_an_entity_highlights_the_schemas_holding_it(model) -> None:
    """With non-exclusive membership, editing one entity can affect several
    deliverables, and that has to be visible before the edit."""
    customer = by_name(model.entities, "Customer")
    result = selection.focus(model, selection.Selection(entity=customer.uuid))
    assert len(result.contains) == 2


def test_uses_and_references_are_kept_apart(model) -> None:
    """An entity's own properties and the entities it points at are different
    relationships, and the interface colours them differently."""
    order = by_name(model.entities, "Order")
    result = selection.focus(model, selection.Selection(entity=order.uuid))
    assert not (result.uses & result.references)


def test_a_property_highlights_its_type(model) -> None:
    amount = by_name(model.properties, "amount")
    money = by_name(model.types, "Money")
    result = selection.focus(model, selection.Selection(property=amount.uuid))
    assert money.uuid in result.uses


def test_a_type_highlights_its_validators_and_its_parent(model) -> None:
    positive = by_name(model.types, "PositiveMoney")
    money = by_name(model.types, "Money")
    result = selection.focus(model, selection.Selection(type=positive.uuid))
    assert money.uuid in result.references
    assert result.uses  # the positive built-in


# --- follow selection -------------------------------------------------------


def test_tags_name_the_relationship(model) -> None:
    order = by_name(model.entities, "Order")
    customer = by_name(model.entities, "Customer")
    result = selection.focus(model, selection.Selection(entity=order.uuid))
    assert selection.tags_for(customer.uuid, result) == ("references",)


# --- updating the selection -------------------------------------------------


def test_choosing_a_context_clears_the_rest(model) -> None:
    """The Context filters every other column, so a selection made before the
    change may name an item that is no longer visible."""
    order = by_name(model.entities, "Order")
    common = ctx(model, "common")
    support = ctx(model, "support")
    current = selection.Selection(context=common, entity=order.uuid)
    after = selection.updated(current, "context", support)
    assert after.context == support
    assert after.entity is None


def test_choosing_anything_else_keeps_the_context(model) -> None:
    order = by_name(model.entities, "Order")
    sales = ctx(model, "sales")
    after = selection.updated(selection.Selection(context=sales), "entity", order.uuid)
    assert after.context == sales
    assert after.entity == order.uuid


def test_selections_in_different_columns_accumulate(model) -> None:
    sales = ctx(model, "sales")
    order = by_name(model.entities, "Order")
    money = by_name(model.types, "Money")
    current = selection.Selection(context=sales)
    current = selection.updated(current, "entity", order.uuid)
    current = selection.updated(current, "type", money.uuid)
    assert current.entity == order.uuid and current.type == money.uuid


def test_deselecting_a_column_clears_only_that_one(model) -> None:
    sales = ctx(model, "sales")
    order = by_name(model.entities, "Order")
    current = selection.updated(selection.Selection(context=sales), "entity", order.uuid)
    after = selection.updated(current, "entity", None)
    assert after.entity is None
    assert after.context == sales


def test_updating_does_not_need_a_dunder_dict(model) -> None:
    """Selection is a slots dataclass. Building the next one by unpacking
    __dict__ raised inside a Tk callback, where the exception was swallowed and
    selection silently did nothing."""
    with pytest.raises(AttributeError):
        _ = selection.Selection().__dict__
    assert selection.updated(selection.Selection(), "type", None) == selection.Selection()


# --- revealing rather than filtering -----------------------------------------


def test_a_related_row_is_pointed_at_not_isolated(model) -> None:
    """Selecting a property highlights its type and scrolls to it.

    Filtering was tried here and removed: it reduced a fourteen-row Type column
    to the one row already highlighted, which says nothing new and takes away
    everything you might compare it against.
    """
    amount = by_name(model.properties, "amount")
    money = by_name(model.types, "Money")
    result = selection.focus(model, selection.Selection(property=amount.uuid))
    ids = [t.uuid for t in model.types]
    assert selection.reveal_target(ids, result) == money.uuid


def test_nothing_related_means_nothing_to_scroll_to(model) -> None:
    ids = [t.uuid for t in model.types]
    assert selection.reveal_target(ids, selection.focus(model, selection.Selection())) is None


def test_a_column_with_no_related_row_is_left_alone(model) -> None:
    """An entity highlights properties, not validators; the validator column
    has nothing to say and is not disturbed."""
    order = by_name(model.entities, "Order")
    result = selection.focus(model, selection.Selection(entity=order.uuid))
    assert selection.reveal_target([v.uuid for v in model.validators], result) is None


def test_highlighting_still_names_the_relationship(model) -> None:
    """What filtering used to convey, the tags convey without hiding anything."""
    order = by_name(model.entities, "Order")
    customer = by_name(model.entities, "Customer")
    result = selection.focus(model, selection.Selection(entity=order.uuid))
    assert selection.tags_for(customer.uuid, result) == ("references",)


# --- the context path --------------------------------------------------------


def test_the_context_path_reads_root_first(model) -> None:
    sales = ctx(model, "sales")
    assert [name for _, name in rows.context_path(model, sales)] == ["common", "sales"]


def test_a_root_context_is_its_own_path(model) -> None:
    assert rows.context_label(model, ctx(model, "common")) == "common"


def test_no_context_reads_as_none(model) -> None:
    assert rows.context_label(model, None) == "(none)"


def test_a_cyclic_context_chain_does_not_hang(model) -> None:
    common = by_name(model.contexts, "common")
    sales = by_name(model.contexts, "sales")
    common.parent = sales.uuid
    assert rows.context_path(model, sales.uuid) is not None


# --- a context is always active ---------------------------------------------


def test_the_default_context_is_the_root(model) -> None:
    """Every item belongs to a context, so "no context" is not a state the
    application should sit in: with nothing active the columns show items from
    branches that cannot see each other."""
    assert rows.default_context(model) == ctx(model, "common")


def test_a_model_with_no_contexts_has_no_default() -> None:
    from designer_model import Model

    assert rows.default_context(Model()) is None


def test_the_root_context_hides_the_branches(model) -> None:
    root = rows.default_context(model)
    labels = rows.entities(model, root).labels()
    assert "Customer" in labels  # common
    assert "Order" not in labels  # sales, below
    assert "Ticket" not in labels  # support, below


# --- which selection the editor shows ----------------------------------------


def test_the_last_chosen_column_wins(model) -> None:
    """Not the rightmost. Property sits right of Type, so choosing a Type after
    a Property would otherwise leave the Property in the form."""
    amount = by_name(model.properties, "amount")
    money = by_name(model.types, "Money")
    current = selection.updated(selection.Selection(), "property", amount.uuid)
    assert current.active_item() == amount.uuid
    current = selection.updated(current, "type", money.uuid)
    assert current.active_item() == money.uuid


def test_choosing_the_same_column_twice_keeps_it_active(model) -> None:
    first = by_name(model.types, "Money")
    second = by_name(model.types, "PositiveMoney")
    current = selection.updated(selection.Selection(), "type", first.uuid)
    current = selection.updated(current, "type", second.uuid)
    assert current.active == "type"
    assert current.active_item() == second.uuid


def test_clearing_the_active_column_falls_back(model) -> None:
    amount = by_name(model.properties, "amount")
    money = by_name(model.types, "Money")
    current = selection.updated(selection.Selection(), "property", amount.uuid)
    current = selection.updated(current, "type", money.uuid)
    current = selection.updated(current, "type", None)
    assert current.active == "property"
    assert current.active_item() == amount.uuid


def test_clearing_the_last_selection_leaves_nothing_active(model) -> None:
    money = by_name(model.types, "Money")
    current = selection.updated(selection.Selection(), "type", money.uuid)
    current = selection.updated(current, "type", None)
    assert current.active is None
    assert current.active_item() is None


def test_choosing_a_context_makes_it_active_and_clears_the_rest(model) -> None:
    money = by_name(model.types, "Money")
    current = selection.updated(selection.Selection(), "type", money.uuid)
    current = selection.updated(current, "context", ctx(model, "sales"))
    assert current.active == "context"
    assert current.type is None


def test_an_empty_selection_shows_nothing(model) -> None:
    assert selection.Selection().active_item() is None


def test_choosing_a_base_type_clears_the_type_beside_it(model) -> None:
    money = by_name(model.types, "Money")
    current = selection.updated(selection.Selection(), "type", money.uuid)
    current = selection.choose_base_type(current, "decimal")
    assert current.base_type == "decimal"
    assert current.type is None
    assert current.active == "type"


def test_choosing_a_type_clears_the_base_type(model) -> None:
    money = by_name(model.types, "Money")
    current = selection.choose_base_type(selection.Selection(), "decimal")
    current = selection.updated(current, "type", money.uuid)
    assert current.base_type is None
    assert current.type == money.uuid


def test_a_base_type_selection_survives_a_choice_elsewhere(model) -> None:
    amount = by_name(model.properties, "amount")
    current = selection.choose_base_type(selection.Selection(), "string")
    current = selection.updated(current, "property", amount.uuid)
    assert current.base_type == "string"
    assert current.active == "property"


def test_a_schema_below_the_root_is_not_visible_from_it(model) -> None:
    """Visibility is ancestors-only, and it applies to schemas as much as to
    anything else — which is why a test wanting one has to go there first."""
    root = rows.default_context(model)
    assert rows.schemas(model, root).labels() == []
    assert "sales_schema" in rows.schemas(model, ctx(model, "sales")).labels()


def test_a_property_below_the_root_is_not_visible_from_it(model) -> None:
    root = rows.default_context(model)
    assert "quantity" not in rows.properties(model, root).labels()
    assert "quantity" in rows.properties(model, ctx(model, "sales")).labels()


# --- sorting -----------------------------------------------------------------


def test_a_flat_column_is_alphabetical(model) -> None:
    labels = rows.properties(model, ctx(model, "sales")).labels()
    assert labels == sorted(labels, key=str.lower)


def test_a_flat_column_reverses(model) -> None:
    """A long list is worth reversing rather than scrolling to the end of."""
    ascending = rows.properties(model, ctx(model, "sales")).labels()
    descending = rows.properties(model, ctx(model, "sales"), descending=True).labels()
    assert descending == list(reversed(ascending))


def test_sorting_is_case_insensitive(model) -> None:
    """Otherwise every capitalised name sorts before every lowercase one, which
    is not what anybody means by alphabetical."""
    roots = [r.label for r in rows.types(model, ctx(model, "common")).rows if not r.parent]
    assert roots == sorted(roots, key=str.lower)
    assert roots != sorted(roots), "plain ASCII order would put every capital first"


def test_a_tree_sorts_siblings_not_the_whole_list(model) -> None:
    """Reversing must not put children before their parents: the widget inserts
    in one pass and a forward reference fails."""
    for descending in (False, True):
        data = rows.types(model, ctx(model, "common"), descending=descending)
        seen: set[str] = set()
        for row in data.rows:
            assert row.parent == "" or row.parent in seen
            seen.add(row.id)


def test_reversing_a_tree_reverses_each_level(model) -> None:
    ascending = [r.label for r in rows.types(model, ctx(model, "common")).rows if not r.parent]
    descending = [r.label for r in rows.types(model, ctx(model, "common"), descending=True).rows if not r.parent]
    assert descending == list(reversed(ascending))


def test_built_ins_stay_last_whichever_way_it_sorts(model) -> None:
    """That is a grouping, not a sort key: reversing it would bury the model's
    own validators under forty library entries."""
    for descending in (False, True):
        data = rows.validators(
            model,
            ctx(model, "sales"),
            library=standard_library(),
            show_builtins=True,
            descending=descending,
        )
        first_builtin = next(i for i, r in enumerate(data.rows) if "builtin" in r.tags)
        assert all("builtin" not in r.tags for r in data.rows[:first_builtin])


def test_reversing_still_sorts_within_each_group(model) -> None:
    data = rows.validators(
        model,
        ctx(model, "sales"),
        library=standard_library(),
        show_builtins=True,
        descending=True,
    )
    built_in = [r.label.lower() for r in data.rows if "builtin" in r.tags]
    assert built_in == sorted(built_in, reverse=True)


# --- column widths -----------------------------------------------------------


def test_a_column_wants_three_quarters_of_its_widest_row(model) -> None:
    """The longest name is usually an outlier; sizing to the worst case gives
    six columns that do not fit on a 1024-wide screen."""
    assert rows.preferred_width([40, 120, 200], em=8) == 138  # capped by the column count


def test_a_very_long_name_does_not_squeeze_its_neighbours(model) -> None:
    assert rows.preferred_width([2000], em=8) == 1024 // 7 - 8


def test_a_column_of_short_names_stays_usable(model) -> None:
    assert rows.preferred_width([12, 15], em=8) == rows.minimum_width(8)


def test_an_empty_column_still_has_a_width(model) -> None:
    assert rows.preferred_width([], em=8) > 0


def test_six_columns_at_the_minimum_fit_a_small_screen(model) -> None:
    """Which is the point of the minimum being much smaller than the preferred
    width: a preferred width that cannot be given up is a minimum by another
    name."""
    assert rows.minimum_width(8) * 7 < 1024


def test_the_floor_follows_the_font(model) -> None:
    """Measured in the interface font, so it is not right on one machine and
    wrong on the next."""
    assert rows.minimum_width(16) == 2 * rows.minimum_width(8)


def test_the_interface_column_is_flat(model) -> None:
    """An Interface has no parent and no chain."""
    import datetime as dt
    from uuid import uuid4

    from designer_model.model import Interface

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    model.interfaces.append(
        Interface(
            uuid=uuid4(),
            name="money_uk",
            description="",
            created=now,
            modified=now,
            context=ctx(model, "common"),
            base_type="decimal",
            picture="#,##0.00",
        )
    )
    data = rows.interfaces(model, ctx(model, "common"))
    assert data.labels() == ["money_uk"]
    assert all(row.parent == "" for row in data.rows)


def test_an_unfinished_interface_is_tagged(model) -> None:
    import datetime as dt
    from uuid import uuid4

    from designer_model.model import Interface

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    model.interfaces.append(
        Interface(
            uuid=uuid4(),
            name="half_done",
            description="",
            created=now,
            modified=now,
            context=ctx(model, "common"),
            base_type="decimal",
            picture="",
        )
    )
    assert "incomplete" in rows.interfaces(model, ctx(model, "common")).rows[0].tags


def test_interfaces_come_before_types_in_the_columns(model) -> None:
    """A Type binds them, so it reads left to right."""
    from designer_app.state import COLUMNS

    assert COLUMNS.index("interface") < COLUMNS.index("type")
    assert COLUMNS.index("validator") < COLUMNS.index("interface")


def test_the_ceiling_follows_the_column_count(model) -> None:
    """Fixed, it was set for six columns and a seventh pushed the total past
    the screen it was meant to fit."""
    em = 8
    for count in (6, 7, 10):
        widest = [10_000]
        assert rows.preferred_width(widest, em, columns=count) * count < 1024


def test_a_column_of_short_names_is_not_forced_wide(model) -> None:
    """A flat floor swallowed the calculation for every such column."""
    assert rows.preferred_width([40, 48], 8) < rows.preferred_width([200, 240], 8)


def test_nothing_goes_below_the_absolute_floor(model) -> None:
    assert rows.preferred_width([8], 8) == rows.minimum_width(8)
    assert rows.preferred_width([], 8) == rows.minimum_width(8)


# --- sorting a table in the form ---------------------------------------------


def test_a_heading_click_cycles_through_three_states(model) -> None:
    """Three, not two: stored order has to be reachable again, because in the
    slots table it is the column order of the generated table."""
    column, direction = rows.next_sort(0, -1, rows.STORED)
    assert (column, direction) == (0, rows.ASCENDING)
    column, direction = rows.next_sort(0, column, direction)
    assert (column, direction) == (0, rows.DESCENDING)
    column, direction = rows.next_sort(0, column, direction)
    assert (column, direction) == (-1, rows.STORED)


def test_a_different_heading_starts_at_ascending(model) -> None:
    assert rows.next_sort(2, 0, rows.DESCENDING) == (2, rows.ASCENDING)


def test_stored_order_is_returned_unchanged(model) -> None:
    stored = ["c", "a", "b"]
    assert rows.sorted_rows(stored, {"c": "z", "a": "y", "b": "x"}, rows.STORED) == stored


def test_ascending_sorts_by_the_shown_value(model) -> None:
    keys = {"1": "total", "2": "amount", "3": "Customer"}
    assert rows.sorted_rows(["1", "2", "3"], keys, rows.ASCENDING) == ["2", "3", "1"]


def test_descending_is_the_reverse(model) -> None:
    keys = {"1": "total", "2": "amount", "3": "Customer"}
    assert rows.sorted_rows(["1", "2", "3"], keys, rows.DESCENDING) == ["1", "3", "2"]


def test_sorting_ignores_case(model) -> None:
    """`Customer` belongs between `amount` and `total`, not before both."""
    keys = {"1": "total", "2": "amount", "3": "Customer"}
    assert rows.sorted_rows(["1", "2", "3"], keys, rows.ASCENDING)[1] == "3"


def test_a_row_with_no_value_still_sorts(model) -> None:
    assert rows.sorted_rows(["1", "2"], {"1": "a"}, rows.ASCENDING) == ["2", "1"]
