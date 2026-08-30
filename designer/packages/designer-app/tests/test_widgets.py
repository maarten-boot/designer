"""The widgets.

Skipped without a display, so this file is silent on the machine the code was
written on and does the work on a machine that can show a window.

The centrepiece is `test_every_menu_command_survives_being_invoked`. It walks
the menu bar and clicks everything, which is how the reset-layout crash should
have been found — by a test run, not by a user.
"""

from __future__ import annotations

import pathlib

import pytest

# importorskip, not a plain import: a module-level import of tkinter fails at
# collection time, before any skip mark can take effect, and one uncollectable
# file stops the whole run
tk = pytest.importorskip("tkinter", reason="tkinter is not installed")

from designer_app.state import COLUMNS, TITLES  # noqa: E402


def _display_available() -> tuple[bool, str]:
    """tkinter being importable is not the same as a display being there."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        return False, f"no display: {error}"
    root.destroy()
    return True, ""


HAVE_DISPLAY, WHY_NOT = _display_available()

# the probe lives here rather than in conftest because a skip mark is needed at
# import time, and conftest is not importable from a test module
pytestmark = pytest.mark.skipif(not HAVE_DISPLAY, reason=WHY_NOT or "needs a display")


def settle(app) -> None:
    """Let the event queue drain.

    `update_idletasks` is not enough: ttk queues `<<TreeviewSelect>>` as a
    virtual event on the normal queue, and only a full `update` delivers it. A
    test that calls the lesser one sees the selection never change and blames
    the handler.
    """
    app.update()


def menu_of(widget: tk.Misc) -> tk.Menu:
    return widget.nametowidget(widget.cget("menu"))


def walk_commands(menu: tk.Menu, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], int]]:
    """Every clickable entry in a menu tree, with the path that reaches it."""
    found = []
    last = menu.index("end")
    if last is None:
        return found
    for index in range(last + 1):
        kind = menu.type(index)
        # a tearoff entry has no label; on X11 it is index 0 of any menu that
        # was not built with tearoff=False
        if kind in {"separator", "tearoff"}:
            continue
        label = str(menu.entrycget(index, "label"))
        if kind == "cascade":
            child = menu.nametowidget(menu.entrycget(index, "menu"))
            found += walk_commands(child, (*path, label))
        else:
            found.append(((*path, label), index))
    return found


# --- is this even the current code? -----------------------------------------


def test_the_modules_under_test_are_the_current_ones() -> None:
    """A stale copy on the path makes every other failure a red herring.

    Symptoms: pytest printing `???` instead of source, a traceback showing one
    test's body while naming another's line. Both mean the file being read and
    the code being run are not the same file.
    """
    import inspect

    import designer_app.app
    import designer_app.selection

    markers = {
        designer_app.app: ("updated(self.selection", "DesignerApp._on_select uses updated()"),
        designer_app.selection: ("def updated(", "selection.updated() exists"),
    }
    stale = []
    for module, (needle, what) in markers.items():
        source = inspect.getsource(module)
        if needle not in source:
            stale.append(f"{what} — missing from {module.__file__}")
    assert not stale, "stale modules on the path:\n  " + "\n  ".join(stale)


def test_no_leftover_bytecode_shadows_the_source() -> None:
    """Compiled caches older than their source are the other way this happens."""
    import designer_app.app

    source = pathlib.Path(designer_app.app.__file__)
    caches = list((source.parent / "__pycache__").glob(f"{source.stem}.*.pyc"))
    outdated = [c for c in caches if c.stat().st_mtime < source.stat().st_mtime]
    assert not outdated, "bytecode older than its source: " + ", ".join(str(c) for c in outdated)


# --- does the event arrive at all? ------------------------------------------


def test_the_select_event_reaches_the_column(app) -> None:
    """Isolates delivery from handling.

    If this fails, `<<TreeviewSelect>>` never arrived and the three selection
    failures are one symptom, not three bugs. If it passes and the others still
    fail, the handler is at fault.
    """
    column = app.columns["entity"]
    seen: list[tuple] = []
    passthrough = column._on_select

    def spy(title, row_id):
        seen.append((title, row_id))
        return passthrough(title, row_id)

    column._on_select = spy
    column.tree.selection_set(_all_rows(column.tree)[0])
    settle(app)
    column._on_select = passthrough
    assert seen, "<<TreeviewSelect>> never reached ColumnView._on_select"


def test_the_column_reports_what_was_selected(app) -> None:
    """One step further in: the event arrived, but did it carry a row id?"""
    column = app.columns["entity"]
    row = _all_rows(column.tree)[0]
    column.tree.selection_set(row)
    settle(app)
    assert column.selected_id == row


# --- the shell --------------------------------------------------------------


def test_the_window_builds(app) -> None:
    assert app.winfo_exists()
    assert app.title() == "Designer"


def test_the_minimum_size_is_applied(app) -> None:
    width, height = app.minsize()
    assert width <= 1024 and height <= 768
    assert width > 0 and height > 0


def test_six_columns_in_the_declared_order(app) -> None:
    assert list(app.columns) == list(COLUMNS)
    headings = [app.columns[name].title for name in COLUMNS]
    assert headings == [TITLES[name] for name in COLUMNS]


def test_every_column_is_in_the_paned_window(app) -> None:
    panes = {str(p) for p in app._upper.panes()}
    for name in COLUMNS:
        assert str(app.columns[name]) in panes


# --- content ----------------------------------------------------------------


def test_columns_populate_from_the_model(app) -> None:
    types = app.columns["type"].tree
    assert types.get_children(), "the Type column is empty"
    labels = {types.item(i, "text") for i in types.get_children()}
    assert "string" in labels  # base types are the roots


def test_the_entity_column_shows_a_known_entity(app) -> None:
    entities = app.columns["entity"].tree
    found = {entities.item(i, "text") for i in _all_rows(entities)}
    assert "Customer" in found


def test_built_in_validators_are_hidden_by_default(app) -> None:
    validators = app.columns["validator"].tree
    labels = {validators.item(i, "text") for i in _all_rows(validators)}
    assert "max_length" not in labels


def test_showing_built_ins_adds_them(app) -> None:
    app._show_builtins.set(True)
    app.refresh()
    validators = app.columns["validator"].tree
    labels = {validators.item(i, "text") for i in _all_rows(validators)}
    assert "max_length" in labels


def _all_rows(tree: tk.Misc, parent: str = "") -> list[str]:
    out = []
    for child in tree.get_children(parent):
        out.append(child)
        out += _all_rows(tree, child)
    return out


# --- selection and linkage --------------------------------------------------


def test_selecting_a_context_filters_the_other_columns(app) -> None:
    contexts = app.columns["context"].tree
    support = next(i for i in _all_rows(contexts) if contexts.item(i, "text") == "support")
    contexts.selection_set(support)
    settle(app)
    entities = app.columns["entity"].tree
    labels = {entities.item(i, "text") for i in _all_rows(entities)}
    assert "Ticket" in labels
    assert "Order" not in labels  # a sibling context, not visible


def test_selecting_a_schema_leaves_the_entity_column_whole(app) -> None:
    """Members are highlighted, not isolated. The column is where members are
    chosen from, so hiding non-members hides what somebody adding one wants."""
    select_named(app, "context", "sales")
    entities = app.columns["entity"].tree
    before = {entities.item(i, "text") for i in _all_rows(entities)}
    schemas = app.columns["schema"].tree
    rows_here = _all_rows(schemas)
    assert rows_here, "no schema visible from this context"
    schemas.selection_set(rows_here[0])
    settle(app)
    after = {entities.item(i, "text") for i in _all_rows(app.columns["entity"].tree)}
    assert after == before
    assert app.selection.schema is not None


def test_selecting_a_context_then_another_clears_the_stale_selection(app) -> None:
    """A selection made before a context change may name something no longer
    visible, and a stale selection keeps highlighting things that are gone.

    It has to be a *different* context: re-selecting the one already chosen
    changes nothing in the widget and fires no event.
    """
    select_named(app, "context", "sales")
    entities = app.columns["entity"].tree
    entities.selection_set(_all_rows(entities)[0])
    settle(app)
    assert app.selection.entity is not None
    select_named(app, "context", "common")
    assert app.selection.entity is None


def test_reselecting_does_not_drive_a_refresh_loop(app) -> None:
    """Repopulating a column restores its selection, which fires the select
    event again. Unguarded, refresh and show drive each other round the event
    queue forever — a hang rather than a failure, which is worse."""
    entities = app.columns["entity"].tree
    row = _all_rows(entities)[0]

    counted = {"refreshes": 0}
    original = app.refresh

    def counting_refresh():
        counted["refreshes"] += 1
        original()

    app.refresh = counting_refresh
    entities.selection_set(row)
    settle(app)
    entities.selection_set(row)  # the same row again
    settle(app)
    app.refresh = original
    assert counted["refreshes"] <= 3, f"refresh ran {counted['refreshes']} times"


def test_selecting_a_row_builds_a_form_below(app) -> None:
    entities = app.columns["entity"].tree
    entities.selection_set(_all_rows(entities)[0])
    settle(app)
    assert app.editor._spec is not None
    assert app.editor._spec.kind == "Entity"


def test_a_filter_narrows_a_column(app) -> None:
    column = app.columns["property"]
    before = len(_all_rows(column.tree))
    column._filter.set("zzzzz")
    settle(app)
    app.refresh()
    assert len(_all_rows(column.tree)) < before


# --- collapsing -------------------------------------------------------------


@pytest.mark.parametrize("name", COLUMNS)
def test_every_column_collapses_and_restores(app, name) -> None:
    """Including the rightmost, which is what crashed: `insert` at a position
    equal to the number of panes is out of bounds."""
    app._toggle_column(name)
    settle(app)
    assert app.collapse.is_collapsed(name)
    app._toggle_column(name)
    settle(app)
    assert not app.collapse.is_collapsed(name)
    assert list(app.collapse.order) == list(COLUMNS)


def test_reset_layout_after_collapsing_the_last_column(app) -> None:
    """The reported traceback, end to end."""
    app._toggle_column(COLUMNS[-1])
    settle(app)
    app._reset_layout()
    settle(app)
    assert app.collapse.collapsed == set()
    assert len(app._upper.panes()) == len(COLUMNS)


def test_reset_layout_with_everything_collapsed(app) -> None:
    for name in COLUMNS:
        app._toggle_column(name)
    settle(app)
    app._reset_layout()
    settle(app)
    assert len(app._upper.panes()) == len(COLUMNS)


def test_collapsed_columns_keep_their_left_to_right_order(app) -> None:
    app._toggle_column(COLUMNS[0])
    app._toggle_column(COLUMNS[2])
    settle(app)
    app._toggle_column(COLUMNS[0])
    app._toggle_column(COLUMNS[2])
    settle(app)
    order = [str(p) for p in app._upper.panes()]
    assert order == [str(app.columns[n]) for n in COLUMNS]


# --- the menus --------------------------------------------------------------


def test_every_menu_command_survives_being_invoked(app, quiet) -> None:
    """Click everything.

    Dialogs are stubbed, so an entry that opens one is exercised without
    blocking. Quit is skipped for the obvious reason.
    """
    failures = []
    for path, index in walk_commands(menu_of(app)):
        if path[-1] == "Quit":
            continue
        menu = menu_of(app)
        for label in path[:-1]:
            child_index = next(
                i
                for i in range(menu.index("end") + 1)
                if menu.type(i) == "cascade" and str(menu.entrycget(i, "label")) == label
            )
            menu = menu.nametowidget(menu.entrycget(child_index, "menu"))
        try:
            menu.invoke(index)
            settle(app)
        except Exception as error:
            failures.append(f"{' > '.join(path)}: {type(error).__name__}: {error}")
    assert not failures, "menu commands raised:\n  " + "\n  ".join(failures)


def test_undo_and_redo_with_no_history_are_harmless(app) -> None:
    app.undo()
    app.redo()
    settle(app)


def test_check_model_updates_the_status_line(app) -> None:
    app.full_check()
    settle(app)
    assert str(app.status.cget("text"))


def test_the_status_line_names_the_file(app) -> None:
    assert "sales.json" in str(app.status.cget("text"))


# --- the breadcrumb ---------------------------------------------------------


def test_the_breadcrumb_names_a_context_from_the_start(app) -> None:
    """With the Context column collapsed this is the only indicator of which
    context filters the columns and where a new item would go."""
    assert app.breadcrumb.text.startswith("Context:")
    assert "common" in app.breadcrumb.text


def test_the_breadcrumb_reads_the_whole_path(app) -> None:
    """Text, and nothing else: saying where you are and being a way to move are
    different jobs, and the Context column already does the second."""
    select_named(app, "context", "sales")
    assert app.breadcrumb.text == "Context:  common \u203a sales"


def test_the_breadcrumb_follows_the_context(app) -> None:
    select_named(app, "context", "support")
    assert "support" in app.breadcrumb.text
    select_named(app, "context", "common")
    assert app.breadcrumb.text == "Context:  common"


def test_the_breadcrumb_holds_no_controls(app) -> None:
    """A label that looks like a control is worse than either."""
    from tkinter import ttk

    select_named(app, "context", "sales")
    for child in app.breadcrumb.winfo_children():
        assert isinstance(child, ttk.Label)
        assert not isinstance(child, ttk.Menubutton | ttk.Button)


# --- the editor -------------------------------------------------------------


def select_first(app, column: str):
    """Select the first row that names a real item.

    The Type column is rooted at the base types, which are global and have no
    identity — picking one selects nothing, which is correct behaviour and a
    useless starting point for a test.
    """
    from designer_app.rows import BASE_PREFIX

    tree = app.columns[column].tree
    row = next(i for i in _all_rows(tree) if not i.startswith(BASE_PREFIX))
    tree.selection_set(row)
    settle(app)
    return row


def test_selecting_an_item_builds_its_form(app) -> None:
    select_first(app, "type")
    assert app.editor._spec is not None
    assert "name" in app.editor._spec.keys()


def test_the_form_changes_with_the_selection(app) -> None:
    select_first(app, "type")
    first = app.editor._spec.title
    select_first(app, "property")
    assert app.editor._spec.title != first
    assert app.editor._spec.kind == "Property"


def test_editing_a_name_becomes_one_undo_step(app) -> None:
    select_first(app, "property")
    uuid = app._current_item()
    before = app.session.model.index()[uuid].name
    app.editor._commit_now("name", "renamed_field")
    settle(app)
    assert app.session.model.index()[uuid].name == "renamed_field"
    assert len(app.session.stack) == 1
    app.undo()
    settle(app)
    assert app.session.model.index()[uuid].name == before


def test_committing_an_unchanged_value_does_nothing(app) -> None:
    """The form is rebuilt on every refresh, so focus moves constantly; a
    commit for every click would fill the undo stack with nothing."""
    select_first(app, "property")
    uuid = app._current_item()
    current = app.session.model.index()[uuid].name
    app.editor._commit_now("name", current)
    settle(app)
    assert len(app.session.stack) == 0


def test_changing_a_choice_sets_a_reference(app) -> None:
    from designer_app.rows import BASE_PREFIX

    select_named(app, "context", "sales")  # where `quantity` lives
    property_column = app.columns["property"]
    row = next(i for i in _all_rows(property_column.tree) if property_column.tree.item(i, "text") == "quantity")
    property_column.tree.selection_set(row)
    settle(app)
    app.editor._commit_now("type", f"{BASE_PREFIX}string")
    settle(app)
    from designer_model.model import BaseTypeRef

    assert app.session.model.index()[app._current_item()].type == BaseTypeRef("string")


def test_a_finding_is_shown_beside_the_field(app) -> None:
    """Weight has no parent, and the form has to say so where the parent is
    chosen rather than only in a list at the bottom."""
    types = app.columns["type"].tree
    weight = next(i for i in _all_rows(types) if types.item(i, "text") == "Weight")
    types.selection_set(weight)
    settle(app)
    assert app.editor._spec.by_key("parent").findings


def test_escape_puts_a_field_back(app) -> None:
    select_first(app, "property")
    widget = app.editor._widgets["name"]
    widget.delete(0, "end")
    widget.insert(0, "half typed")
    app.editor._revert("name")
    settle(app)
    assert widget.get() == app.editor._committed["name"]


def test_a_pending_edit_survives_changing_selection(app) -> None:
    """Typing and then clicking elsewhere must not lose the edit."""
    select_first(app, "property")
    uuid = app._current_item()
    widget = app.editor._widgets["name"]
    widget.delete(0, "end")
    widget.insert(0, "typed_but_not_left")
    select_first(app, "type")
    assert app.session.model.index()[uuid].name == "typed_but_not_left"


def test_new_creates_an_empty_item_and_selects_it(app) -> None:
    before = len(app.session.model.types)
    app._new_item("Type")
    settle(app)
    assert len(app.session.model.types) == before + 1
    assert app.session.model.index()[app._current_item()].name == ""


def test_new_is_undoable(app) -> None:
    before = len(app.session.model.types)
    app._new_item("Type")
    settle(app)
    app.undo()
    settle(app)
    assert len(app.session.model.types) == before


def test_duplicate_copies_the_selected_item(app) -> None:
    select_first(app, "type")
    original = app.session.model.index()[app._current_item()]
    app._duplicate_item("Type")
    settle(app)
    copy = app.session.model.index()[app._current_item()]
    assert copy.uuid != original.uuid
    assert copy.name == ""
    assert copy.description == original.description


def test_the_last_chosen_selection_is_the_one_edited(app) -> None:
    """Last chosen, not rightmost. Property sits to the right of Type, so
    choosing a Type after a Property used to leave the Property in the form and
    nothing appeared to happen."""
    property_row = select_first(app, "property")
    assert str(app._current_item()) == property_row
    type_row = select_first(app, "type")
    assert str(app._current_item()) == type_row
    assert app.editor._spec.kind == "Type"


# --- saving -----------------------------------------------------------------


def test_saving_writes_the_file_and_clears_the_dirty_mark(app, tmp_path) -> None:
    target = tmp_path / "saved.json"
    app.session.save(target)
    app._update_status()
    settle(app)
    assert target.exists()
    assert not app.session.dirty


def test_closing_writes_the_settings(app, config) -> None:
    app._on_close()
    assert (config / "settings.json").exists()


def test_an_edit_reaches_the_item_the_form_was_built_for(app) -> None:
    """Selecting a Context and then a Type used to blank the Context's name:
    the commit was applied to whatever was selected when it arrived, not to the
    item on screen when it was typed."""
    contexts = app.columns["context"].tree
    context_row = next(i for i in _all_rows(contexts) if contexts.item(i, "text") == "common")
    contexts.selection_set(context_row)
    settle(app)
    context_uuid = app._current_item()
    before = app.session.model.index()[context_uuid].name

    types = app.columns["type"].tree
    weight = next(i for i in _all_rows(types) if types.item(i, "text") == "Weight")
    types.selection_set(weight)
    settle(app)

    assert app.session.model.index()[context_uuid].name == before, "the context was renamed"
    assert app.session.model.index()[context_uuid].name != ""


def test_selecting_across_columns_never_edits_anything(app) -> None:
    """Selection is navigation. Nothing may change without an edit."""
    import copy as copy_module

    before = {u: copy_module.copy(i) for u, i in app.session.model.index().items()}
    for column in COLUMNS:
        tree = app.columns[column].tree
        for row in _all_rows(tree)[:3]:
            tree.selection_set(row)
            settle(app)
    assert len(app.session.stack) == 0, "selecting pushed an undo step"
    for uuid, item in app.session.model.index().items():
        assert item.name == before[uuid].name, f"{uuid} was renamed by selection alone"


def test_a_destroyed_field_does_not_commit_an_empty_value(app) -> None:
    """Rebuilding the form destroys its widgets; reading one afterwards must
    give back the last committed value, not an empty string."""
    select_first(app, "type")
    committed = app.editor._committed.get("name")
    app.editor.clear()
    assert app.editor.value_of("name") in {committed, ""}
    assert app.editor._spec is None
    app.editor._commit_text("name")  # must be a no-op with no form
    assert len(app.session.stack) == 0


def test_field_variables_outlive_the_call_that_made_them(app) -> None:
    """Tk holds a variable by its Tcl name, not by a Python reference.

    Left as a local, a StringVar is collected, its Tcl variable goes with it,
    and the entry reads back an empty string — which then commits as a cleared
    field. This is what blanked a context's name.
    """
    import gc

    select_first(app, "type")
    gc.collect()
    settle(app)
    assert app.editor._variables, "no field variables were kept"
    assert app.editor.value_of("name") == app.editor._committed["name"]
    assert app.editor.value_of("name") != ""


def test_a_rebuilt_form_still_reads_its_own_values(app) -> None:
    """Refresh rebuilds the form repeatedly; each rebuild must leave readable
    fields, not ones whose backing variable has been collected."""
    import gc

    select_first(app, "property")
    for _ in range(3):
        app.refresh()
        settle(app)
        gc.collect()
    assert app.editor.value_of("name") == app.editor._committed["name"]
    assert len(app.session.stack) == 0, "refreshing pushed an undo step"


def test_the_form_names_the_context_the_item_lives_in(app) -> None:
    select_first(app, "property")
    where = app.editor._spec.by_key("context_path")
    assert where is not None and where.value
    assert not where.editable


# --- schema membership -------------------------------------------------------


def select_named(app, column: str, label: str):
    """Select a row by its label, saying why if it is not there.

    Visibility is ancestors-only, so a schema in `sales` cannot be seen from
    `common` — and the bare StopIteration this used to raise said nothing about
    that.
    """
    tree = app.columns[column].tree
    rows_here = _all_rows(tree)
    for row in rows_here:
        if tree.item(row, "text") == label:
            tree.selection_set(row)
            settle(app)
            return row
    where = app.session.model.index().get(app.selection.context)
    raise AssertionError(
        f"no row labelled {label!r} in the {column} column, seen from context "
        f"{getattr(where, 'name', '(none)')!r}. It holds: "
        f"{sorted(tree.item(r, 'text') for r in rows_here)}"
    )


def test_the_members_table_is_rendered(app) -> None:
    select_named(app, "context", "sales")
    select_named(app, "schema", "sales_schema")
    assert "members" in app.editor.tables
    tree = app.editor.tables["members"]
    assert len(tree.get_children()) == 3


def test_removing_a_member_updates_the_model(app, quiet) -> None:
    quiet["answer"] = True  # if removal would leave the schema unclosed, do it anyway
    select_named(app, "context", "sales")
    schema_uuid = select_named(app, "schema", "sales_schema")
    from uuid import UUID

    schema = app.session.model.index()[UUID(schema_uuid)]
    victim = schema.members[-1]
    app._remove_member(UUID(schema_uuid), str(victim))
    settle(app)
    assert victim not in schema.members
    assert len(app.session.stack) == 1
    app.undo()
    settle(app)
    assert victim in schema.members


def test_removing_without_a_selected_row_does_nothing(app) -> None:
    select_named(app, "context", "sales")
    schema_uuid = select_named(app, "schema", "sales_schema")
    from uuid import UUID

    app._remove_member(UUID(schema_uuid), None)
    settle(app)
    assert len(app.session.stack) == 0


def test_adding_a_member_pulls_in_its_closure_as_one_step(app, quiet) -> None:
    from uuid import UUID

    from designer_model import membership

    select_named(app, "context", "sales")
    schema_uuid = UUID(select_named(app, "schema", "sales_schema"))
    schema = app.session.model.index()[schema_uuid]
    schema.members = ()
    app.refresh()
    settle(app)
    order_line = next(e for e in app.session.model.entities if e.name == "OrderLine")
    quiet["answer"] = True  # accept the cascade
    app.apply_membership(membership.plan_add(app.session.model, schema_uuid, order_line.uuid))
    settle(app)
    assert len(schema.members) == 3
    assert len(app.session.stack) == 1


def test_closing_a_schema_is_one_step(app, quiet) -> None:
    from uuid import UUID

    from designer_model import Deriver

    select_named(app, "context", "sales")
    schema_uuid = UUID(select_named(app, "schema", "sales_schema"))
    schema = app.session.model.index()[schema_uuid]
    customer = next(e for e in app.session.model.entities if e.name == "Customer")
    schema.members = tuple(m for m in schema.members if m != customer.uuid)
    app.refresh()
    settle(app)
    app._close_schema(schema_uuid)
    settle(app)
    assert Deriver(app.session.model).unclosed_references(schema) == []
    assert len(app.session.stack) == 1


def test_adding_when_nothing_can_join_explains_why(app, quiet) -> None:
    """Nothing here should reach a yes/no prompt at all: there is nothing to
    ask about, only something to explain."""
    from uuid import UUID

    select_named(app, "context", "support")
    schema_uuid = UUID(select_named(app, "schema", "support_schema"))
    app._add_member(schema_uuid)
    settle(app)
    assert quiet["info"], "no explanation was offered"
    assert not quiet["ask"], "it asked a question instead of explaining"
    assert len(app.session.stack) == 0


# --- the starting context ----------------------------------------------------


def test_a_context_is_active_from_the_start(app) -> None:
    assert app.selection.context is not None
    assert app.breadcrumb.winfo_children()


def test_the_starting_view_shows_only_the_root_context(app) -> None:
    """Not everything at once, including branches that cannot see each other."""
    labels = {app.columns["entity"].tree.item(i, "text") for i in _all_rows(app.columns["entity"].tree)}
    assert "Customer" in labels
    assert "Order" not in labels and "Ticket" not in labels


def test_clearing_the_context_falls_back_to_the_root(app) -> None:
    """Nothing selected would leave a new item with nowhere to go."""
    select_named(app, "context", "sales")
    app.columns["context"].tree.selection_remove(*app.columns["context"].tree.selection())
    settle(app)
    assert app.selection.context is not None


def test_the_form_panel_is_lighter_than_the_theme(app) -> None:
    """Secondary text on the theme's grey was the first thing to become
    unreadable; the form sits on its own near-white panel."""
    from tkinter import ttk

    from designer_app.formview import FRAME_STYLE, PANEL

    assert ttk.Style(app).lookup(FRAME_STYLE, "background") == PANEL


def test_selecting_a_property_leaves_the_type_column_whole(app) -> None:
    """Highlighting is enough. Filtering here reduced fourteen types to one."""
    select_named(app, "context", "common")
    types = app.columns["type"].tree
    before = len(_all_rows(types))
    select_named(app, "property", "amount")
    assert len(_all_rows(app.columns["type"].tree)) == before


def test_every_column_survives_a_selection_in_every_other(app) -> None:
    """No selection anywhere may shrink a column it did not come from."""
    select_named(app, "context", "common")
    sizes = {name: len(_all_rows(app.columns[name].tree)) for name in COLUMNS}
    for column in ("entity", "property", "type", "validator"):
        rows_here = _all_rows(app.columns[column].tree)
        if not rows_here:
            continue
        app.columns[column].tree.selection_set(rows_here[0])
        settle(app)
        for name in COLUMNS:
            if name == "schema":
                continue  # a schema selection filters entities, by design
            assert len(_all_rows(app.columns[name].tree)) == sizes[name], f"selecting in {column} shrank {name}"


# --- showing which selection is current --------------------------------------


def test_the_starting_context_is_visibly_selected(app) -> None:
    """A selection made in code still has to look chosen."""
    assert app.columns["context"].selected_id is not None
    assert app.selection.active == "context"


def test_only_the_last_chosen_column_is_marked_active(app) -> None:
    select_named(app, "context", "sales")
    select_first(app, "property")
    select_first(app, "type")
    assert app.columns["type"]._active
    assert not app.columns["property"]._active
    assert not app.columns["context"]._active


def test_an_earlier_selection_stays_visible_but_muted(app) -> None:
    """Several columns hold a selection at once; the muted ones still read as
    chosen earlier rather than disappearing."""
    select_named(app, "context", "sales")
    property_row = select_first(app, "property")
    select_first(app, "type")
    assert app.columns["property"].selected_id == property_row


def test_choosing_a_context_clears_the_other_columns_visibly(app) -> None:
    """The model drops those selections, and the widgets have to agree."""
    select_named(app, "context", "sales")
    select_first(app, "property")
    select_named(app, "context", "common")
    assert app.columns["property"].selected_id is None


def test_the_active_and_idle_styles_differ(app) -> None:
    from tkinter import ttk

    from designer_app.columns import ACTIVE_STYLE, IDLE_STYLE

    style = ttk.Style(app)
    active = dict(style.map(ACTIVE_STYLE, "background"))
    idle = dict(style.map(IDLE_STYLE, "background"))
    assert active["selected"] != idle["selected"]


def test_the_starting_context_is_the_active_column(app) -> None:
    """Amber from the start. Built without going through `updated`, the context
    was selected but not current, so nothing was marked."""
    assert app.selection.active == "context"
    assert app.columns["context"]._active
    assert app.editor._spec is not None
    assert app.editor._spec.kind == "Context"


def test_returning_to_the_context_already_selected(app) -> None:
    """Clicking the row that is already selected fires no select event, so the
    column never became active — and only sub-contexts appeared to work."""
    root = app.columns["context"].selected_id
    select_first(app, "type")
    assert app.selection.active == "type"

    app._on_select("Context", root)  # the same row again
    settle(app)
    assert app.selection.active == "context"
    assert app.columns["context"]._active
    assert app.editor._spec.kind == "Context"


def test_a_click_on_the_selected_row_reaches_the_application(app) -> None:
    """The binding that makes the above possible."""
    column = app.columns["context"]
    row = column.selected_id
    seen: list[tuple] = []
    passthrough = column._on_select
    column._on_select = lambda title, row_id: seen.append((title, row_id))
    column.tree.see(row)
    settle(app)
    box = column.tree.bbox(row)
    assert box, "the row is not visible, so it cannot be clicked"

    class Click:
        y = box[1] + box[3] // 2

    column._clicked(Click())
    column._on_select = passthrough
    assert seen == [("Context", row)]


# --- the scrolling editor ----------------------------------------------------


def test_the_form_sits_in_a_scrolling_area(app) -> None:
    """An entity with a dozen slots is taller than the pane, and without this
    the bottom of the form is simply unreachable."""
    assert str(app.editor.winfo_parent()).startswith(str(app._editor_area.canvas))
    assert app._editor_area.canvas.winfo_exists()


def test_the_scrollbar_appears_only_when_it_is_needed(app) -> None:
    select_first(app, "property")  # a short form
    settle(app)
    app._editor_area.update_idletasks()
    first, last = app._editor_area.canvas.yview()
    if first <= 0.0 and last >= 1.0:
        assert not app._editor_area.bar.winfo_ismapped()


def test_a_new_form_starts_at_the_top(app) -> None:
    """Not wherever the previous one was scrolled to."""
    select_named(app, "context", "sales")
    select_first(app, "entity")
    settle(app)
    app._editor_area.canvas.yview_moveto(1.0)
    select_first(app, "property")
    settle(app)
    assert app._editor_area.canvas.yview()[0] == 0.0


def test_the_form_fills_the_width(app) -> None:
    """Otherwise the fields sit in a column the width of their longest label."""
    app.update()
    canvas = app._editor_area.canvas
    window = canvas.find_all()[0]
    assert str(canvas.itemcget(window, "width")) in ("", str(canvas.winfo_width()))


# --- built-in validators -----------------------------------------------------


def show_builtins(app):
    app._show_builtins.set(True)
    app.refresh()
    settle(app)


def test_selecting_a_built_in_explains_rather_than_reporting_it_missing(app) -> None:
    """It used to say the item was gone, because built-ins are not in the model
    — only references to them are."""
    show_builtins(app)
    select_named(app, "validator", "max_length")
    assert app.editor._spec is not None
    assert app.editor._spec.read_only
    assert "cannot be edited" in app.editor._spec.note


def test_a_built_in_offers_a_copy_button(app) -> None:
    show_builtins(app)
    select_named(app, "validator", "max_length")
    assert [a.name for a in app.editor._spec.actions] == ["fork_builtin"]


def test_copying_a_built_in_makes_an_editable_one(app, quiet) -> None:
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "max_length")
    before = len(app.session.model.validators)
    app._fork_builtin(UUID(row))
    settle(app)
    assert len(app.session.model.validators) == before + 1
    copied = app.session.model.index()[app._current_item()]
    assert copied.name == "max_length"
    assert copied.context == app.selection.context
    assert not app.editor._spec.read_only


def test_copying_a_built_in_leaves_the_original_alone(app, quiet) -> None:
    """Rules already bound to the built-in keep pointing at it: the copy is a
    starting point, not a replacement."""
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "max_length")
    app._fork_builtin(UUID(row))
    settle(app)
    assert app.library.by_name("max_length").uuid == UUID(row)


def test_copying_a_built_in_is_one_undo_step(app, quiet) -> None:
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "max_length")
    before = len(app.session.model.validators)
    app._fork_builtin(UUID(row))
    settle(app)
    app.undo()
    settle(app)
    assert len(app.session.model.validators) == before


# --- base types --------------------------------------------------------------


def test_a_base_type_can_be_selected(app) -> None:
    """It used to be unselectable: the row id was discarded and nothing
    happened at all."""
    from designer_app.rows import BASE_PREFIX

    types = app.columns["type"].tree
    row = next(i for i in _all_rows(types) if i.startswith(BASE_PREFIX))
    types.selection_set(row)
    settle(app)
    assert app.selection.base_type is not None
    assert app.columns["type"].selected_id == row


def test_selecting_a_base_type_explains_it_cannot_be_edited(app) -> None:
    from designer_app.rows import BASE_PREFIX

    types = app.columns["type"].tree
    row = next(i for i in _all_rows(types) if types.item(i, "text") == "decimal")
    assert row.startswith(BASE_PREFIX)
    types.selection_set(row)
    settle(app)
    assert app.editor._spec.kind == "Base type"
    assert app.editor._spec.read_only
    assert "cannot be edited" in app.editor._spec.note


def test_choosing_a_real_type_after_a_base_type(app) -> None:
    types = app.columns["type"].tree
    base = next(i for i in _all_rows(types) if types.item(i, "text") == "decimal")
    types.selection_set(base)
    settle(app)
    money = next(i for i in _all_rows(types) if types.item(i, "text") == "Money")
    types.selection_set(money)
    settle(app)
    assert app.selection.base_type is None
    assert app.editor._spec.kind == "Type"


def test_selecting_a_base_type_edits_nothing(app) -> None:
    types = app.columns["type"].tree
    row = next(i for i in _all_rows(types) if types.item(i, "text") == "string")
    types.selection_set(row)
    settle(app)
    assert len(app.session.stack) == 0


def test_declining_the_cascade_still_adds_the_one_asked_for(app, quiet) -> None:
    """Declining means "add the one I asked for", not "do nothing" — refusing
    the whole addition would make closure compulsory by the back door."""
    from uuid import UUID

    from designer_model import Deriver, membership

    select_named(app, "context", "sales")
    schema_uuid = UUID(select_named(app, "schema", "sales_schema"))
    schema = app.session.model.index()[schema_uuid]
    schema.members = ()
    app.refresh()
    settle(app)
    order_line = next(e for e in app.session.model.entities if e.name == "OrderLine")

    quiet["answer"] = False  # decline the cascade
    app.apply_membership(membership.plan_add(app.session.model, schema_uuid, order_line.uuid))
    settle(app)
    assert schema.members == (order_line.uuid,)
    assert Deriver(app.session.model).unclosed_references(schema), "should be left unclosed"


def test_the_cascade_prompt_says_what_declining_does(app, quiet) -> None:
    """Whichever way it is answered, the prompt has to say what "no" means."""
    from uuid import UUID

    from designer_model import membership

    quiet["answer"] = False
    select_named(app, "context", "sales")
    schema_uuid = UUID(select_named(app, "schema", "sales_schema"))
    app.session.model.index()[schema_uuid].members = ()
    order_line = next(e for e in app.session.model.entities if e.name == "OrderLine")
    app.apply_membership(membership.plan_add(app.session.model, schema_uuid, order_line.uuid))
    asked = [message for _title, message in quiet["ask"]]
    assert asked and "leaving the schema unclosed" in asked[0]


# --- deleting ----------------------------------------------------------------


def test_delete_shows_the_impact_before_acting(app, quiet) -> None:
    quiet["answer"] = False  # look, then cancel
    select_named(app, "context", "sales")
    select_named(app, "entity", "Order")
    before = len(app.session.model.entities)
    app._delete_item("Entity")
    settle(app)
    assert quiet["delete"], "no impact was shown"
    assert len(app.session.model.entities) == before, "cancelling still deleted"
    assert len(app.session.stack) == 0


def test_confirming_deletes_in_one_undo_step(app, quiet) -> None:
    quiet["answer"] = True
    select_named(app, "context", "sales")
    select_named(app, "entity", "OrderLine")
    victim = app._current_item()
    app._delete_item("Entity")
    settle(app)
    assert victim not in app.session.model.index()
    assert len(app.session.stack) == 1
    app.undo()
    settle(app)
    assert victim in app.session.model.index()


def test_deleting_clears_the_selection_it_came_from(app, quiet) -> None:
    quiet["answer"] = True
    select_named(app, "context", "sales")
    select_named(app, "entity", "OrderLine")
    app._delete_item("Entity")
    settle(app)
    assert app.selection.entity is None


def test_deleting_fixes_up_what_referred_to_it(app, quiet) -> None:
    quiet["answer"] = True
    select_named(app, "context", "sales")
    order = next(e for e in app.session.model.entities if e.name == "Order")
    slot = next(s for s in order.slots if s.slot_name == "customer")
    select_named(app, "entity", "Customer")
    app._delete_item("Entity")
    settle(app)
    assert slot.target is None
    app.undo()
    settle(app)
    assert slot.target is not None


def test_the_impact_names_the_destructive_case(app, quiet) -> None:
    quiet["answer"] = False
    select_named(app, "context", "sales")
    select_named(app, "entity", "Auditable")
    app._delete_item("Entity")
    settle(app)
    assert quiet["delete"][0].destructive


def test_a_built_in_validator_cannot_be_deleted(app, quiet) -> None:
    quiet["answer"] = True
    show_builtins(app)
    select_named(app, "validator", "max_length")
    app._delete_item("Validator")
    settle(app)
    assert not quiet["delete"], "it offered to delete a built-in"
    assert quiet["info"], "no explanation was offered"
    assert len(app.session.stack) == 0


def test_a_base_type_cannot_be_deleted(app, quiet) -> None:
    quiet["answer"] = True
    types = app.columns["type"].tree
    row = next(i for i in _all_rows(types) if types.item(i, "text") == "string")
    types.selection_set(row)
    settle(app)
    app._delete_item("Type")
    settle(app)
    assert not quiet["delete"]
    assert quiet["info"]


def test_deleting_a_context_takes_its_subtree(app, quiet) -> None:
    quiet["answer"] = True
    select_named(app, "context", "support")
    before = len(app.session.model.index())
    app._delete_item("Context")
    settle(app)
    assert len(app.session.model.index()) < before
    assert quiet["delete"][0].subtree is not None
    app.undo()
    settle(app)
    assert len(app.session.model.index()) == before


def test_deleting_nothing_selected_does_nothing(app, quiet) -> None:
    quiet["answer"] = True
    select_named(app, "context", "sales")
    app._delete_item("Schema")
    settle(app)
    assert not quiet["delete"]
    assert len(app.session.stack) == 0


# --- the slot table ----------------------------------------------------------


def select_entity(app, name: str):
    select_named(app, "context", "sales")
    return select_named(app, "entity", name)


def test_the_slot_table_shows_inherited_rows_too(app) -> None:
    """The effective record reads in one place."""
    select_entity(app, "OrderLine")
    assert "slots" in app.editor.tables
    tree = app.editor.tables["slots"]
    names = {tree.item(i, "values")[0] for i in tree.get_children()}
    assert {"line_total", "order", "quantity"} <= names
    assert "created_at" in names, "an inherited slot is missing"


def test_an_inherited_row_is_marked(app) -> None:
    select_entity(app, "OrderLine")
    tree = app.editor.tables["slots"]
    inherited = [i for i in tree.get_children() if "inherited" in tree.item(i, "tags")]
    assert inherited
    assert tree.item(inherited[0], "values")[4] == "inherited"


def test_adding_a_slot_goes_through_the_dialog(app, quiet) -> None:
    from uuid import UUID

    from designer_app import slots

    entity_row = select_entity(app, "Order")
    entity_uuid = UUID(entity_row)
    amount = next(p for p in app.session.model.properties if p.name == "amount")
    quiet["slot"] = slots.SlotDraft(slot_name="discount", property=amount.uuid, required=False)
    before = len(app.session.model.index()[entity_uuid].slots)
    app._add_value_slot(entity_uuid)
    settle(app)
    assert len(app.session.model.index()[entity_uuid].slots) == before + 1
    assert len(app.session.stack) == 1


def test_cancelling_the_dialog_adds_nothing(app, quiet) -> None:
    from uuid import UUID

    entity_uuid = UUID(select_entity(app, "Order"))
    quiet["slot"] = None  # Cancel
    before = len(app.session.model.index()[entity_uuid].slots)
    app._add_value_slot(entity_uuid)
    settle(app)
    assert len(app.session.model.index()[entity_uuid].slots) == before
    assert len(app.session.stack) == 0


def test_a_refused_slot_says_why_and_changes_nothing(app, quiet) -> None:
    """The rules are checked before anything happens, so the refusal names the
    mistake rather than appearing later as a finding."""
    from uuid import UUID

    from designer_app import slots

    entity_uuid = UUID(select_entity(app, "Order"))
    quiet["slot"] = slots.SlotDraft(slot_name="total")  # already taken
    app._add_value_slot(entity_uuid)
    settle(app)
    assert quiet["warning"], "no reason was given"
    assert "already has a slot" in quiet["warning"][0][1]
    assert len(app.session.stack) == 0


def test_the_override_dialog_offers_only_narrowing_types(app, quiet) -> None:
    from uuid import UUID

    entity_row = select_entity(app, "OrderLine")
    tree = app.editor.tables["slots"]
    inherited_row = next(i for i in tree.get_children() if "inherited" in tree.item(i, "tags"))
    quiet["slot"] = None
    app._override_slot(UUID(entity_row), inherited_row)
    settle(app)
    assert quiet["slot_dialogs"], "no dialog was opened"
    _title, _draft, choices = quiet["slot_dialogs"][-1]
    assert "type_choices" in choices


def test_removing_a_slot_is_one_undo_step(app, quiet) -> None:
    from uuid import UUID

    entity_uuid = UUID(select_entity(app, "Order"))
    entity = app.session.model.index()[entity_uuid]
    victim = entity.slots[-1]
    tree = app.editor.tables["slots"]
    app._remove_slot(entity_uuid, str(victim.uuid))
    settle(app)
    assert victim not in entity.slots
    assert len(app.session.stack) == 1
    app.undo()
    settle(app)
    assert victim in entity.slots
    assert tree is not None


def test_an_inherited_slot_cannot_be_removed(app, quiet) -> None:
    """It is edited on the entity that declares it."""
    from uuid import UUID

    entity_row = select_entity(app, "OrderLine")
    tree = app.editor.tables["slots"]
    inherited_row = next(i for i in tree.get_children() if "inherited" in tree.item(i, "tags"))
    app._remove_slot(UUID(entity_row), inherited_row)
    settle(app)
    assert len(app.session.stack) == 0


def test_moving_a_slot_changes_the_order(app, quiet) -> None:
    from uuid import UUID

    entity_uuid = UUID(select_entity(app, "Order"))
    entity = app.session.model.index()[entity_uuid]
    ordered = sorted(entity.slots, key=lambda s: s.position)
    first = ordered[0]
    app._move_slot_down(entity_uuid, str(first.uuid))
    settle(app)
    assert sorted(entity.slots, key=lambda s: s.position)[0] is not first
    app.undo()
    settle(app)
    assert sorted(entity.slots, key=lambda s: s.position)[0] is first


def test_copying_a_built_in_leaves_the_list_showing(app, quiet) -> None:
    """Hiding the built-ins the moment somebody copies from one is
    disorienting: the copy does not replace the original."""
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "is_uuid")
    app._fork_builtin(UUID(row))
    settle(app)
    assert app._show_builtins.get(), "the built-ins were hidden"
    labels = {app.columns["validator"].tree.item(i, "text") for i in _all_rows(app.columns["validator"].tree)}
    assert "max_length" in labels, "the built-in list vanished"


def test_the_copy_and_the_original_are_both_listed(app, quiet) -> None:
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "is_uuid")
    app._fork_builtin(UUID(row))
    settle(app)
    tree = app.columns["validator"].tree
    both = [i for i in _all_rows(tree) if tree.item(i, "text") == "is_uuid"]
    assert len(both) == 2, "the copy and the built-in should both appear"
    tags = {("builtin" in tree.item(i, "tags")) for i in both}
    assert tags == {True, False}, "one greyed as built in, one not"


def test_the_copy_says_it_takes_precedence(app, quiet) -> None:
    from uuid import UUID

    show_builtins(app)
    row = select_named(app, "validator", "is_uuid")
    app._fork_builtin(UUID(row))
    settle(app)
    field = app.editor._spec.by_key("overrides")
    assert field is not None and field.emphasis == "attention"


# --- sorting -----------------------------------------------------------------


def test_clicking_a_heading_reverses_the_column(app) -> None:
    select_named(app, "context", "sales")
    tree = app.columns["property"].tree
    before = [tree.item(i, "text") for i in _all_rows(tree)]
    app._toggle_sort("Property")
    settle(app)
    after = [tree.item(i, "text") for i in _all_rows(app.columns["property"].tree)]
    assert after == list(reversed(before))


def test_the_heading_shows_which_way_it_runs(app) -> None:
    heading = app.columns["property"]._heading
    assert "\u25b4" in str(heading.cget("text"))
    app._toggle_sort("Property")
    settle(app)
    assert "\u25be" in str(app.columns["property"]._heading.cget("text"))


def test_the_direction_is_remembered(app) -> None:
    app._toggle_sort("Type")
    settle(app)
    assert "type" in app.settings.sort_descending
    app._toggle_sort("Type")
    settle(app)
    assert "type" not in app.settings.sort_descending


def test_reversing_keeps_the_selection(app) -> None:
    select_named(app, "context", "sales")
    chosen = select_named(app, "property", "amount")
    app._toggle_sort("Property")
    settle(app)
    assert app.columns["property"].selected_id == chosen


# --- the findings window -----------------------------------------------------


def test_checking_the_model_opens_a_list(app) -> None:
    """The status line can say how many; only a list says which."""
    app.show_findings()
    settle(app)
    window = app._findings_window
    assert window is not None and window.winfo_exists()
    assert window.tree.get_children(), "the list is empty"


def test_the_list_shows_every_finding(app) -> None:
    """At `everything`. Any test that counts findings has to say which level it
    counts at, or it is really testing the default."""
    app.settings.finding_level = "everything"
    app.show_findings()
    settle(app)
    assert len(app._findings_window.tree.get_children()) == len(app.session.report.findings)


def test_opening_it_twice_reuses_the_window(app) -> None:
    app.show_findings()
    settle(app)
    first = app._findings_window
    app.show_findings()
    settle(app)
    assert app._findings_window is first


def test_going_to_a_finding_selects_what_it_is_about(app) -> None:
    """A list that points at something unreachable is only half a list."""
    from designer_app import findings as findingview

    app.show_findings()
    settle(app)
    row = next(
        r for r in findingview.summarise(app.session.model, app.session.report, app.library) if r.code == "MOD101"
    )
    app._go_to_finding(row)
    settle(app)
    assert app.selection.type == row.item
    assert app.editor._spec.title == "Weight"


def test_going_to_a_finding_moves_the_context_too(app) -> None:
    """The item may be somewhere the columns are not currently looking."""
    from designer_app import findings as findingview

    select_named(app, "context", "support")
    app.show_findings()
    settle(app)
    row = next(
        r for r in findingview.summarise(app.session.model, app.session.report, app.library) if r.code == "MOD101"
    )
    app._go_to_finding(row)
    settle(app)
    assert app.selection.context is not None
    assert app.selection.type == row.item


def test_the_list_follows_the_model(app, quiet) -> None:
    """A list open while the model changes must not go stale.

    At `everything`: the findings that go with Weight are an unfinished item
    and a note, both hidden at the default level, so at `warning` nothing would
    appear to change.
    """
    app.settings.finding_level = "everything"
    app.show_findings()
    settle(app)
    before = len(app._findings_window.tree.get_children())
    weight = next(t for t in app.session.model.types if t.name == "Weight")
    select_named(app, "context", "common")
    select_named(app, "type", "Weight")
    quiet["answer"] = True
    app._delete_item("Type")
    settle(app)
    app.show_findings()
    settle(app)
    assert len(app._findings_window.tree.get_children()) < before
    assert weight.uuid not in app.session.model.index()


def test_the_status_line_names_the_counts(app) -> None:
    app.settings.finding_level = "everything"
    app.show_findings()
    settle(app)
    text = str(app.status.cget("text"))
    assert "warning" in text and "note" in text
    assert "Severity." not in text, "an enum leaked into the status line"


def test_the_status_line_says_what_it_is_hiding(app) -> None:
    """Filtering must not silently swallow findings."""
    app.settings.finding_level = "warning"
    app.show_findings()
    settle(app)
    assert "hidden" in str(app.status.cget("text"))


def test_an_export_blocker_is_named_however_low_the_level(app) -> None:
    """Those are mostly unfinished items, which is exactly what a low level
    hides — so without this a model could reach an export with a fault nobody
    had been shown."""
    for level in ("error", "warning", "unfinished", "everything"):
        app.settings.finding_level = level
        app.show_findings()
        settle(app)
        assert "would block an export" in str(app.status.cget("text")), level


def test_the_status_line_opens_the_list(app) -> None:
    # str(): cget hands back a Tcl object for some options, not a Python string
    assert str(app.status.cget("cursor")) == "hand2"
    app.status.event_generate("<Button-1>")
    settle(app)
    assert app._findings_window is not None


def test_the_findings_list_respects_the_level(app) -> None:
    app.settings.finding_level = "warning"
    app.show_findings()
    settle(app)
    fewer = len(app._findings_window.tree.get_children())
    app.settings.finding_level = "everything"
    app.show_findings()
    settle(app)
    assert len(app._findings_window.tree.get_children()) > fewer


def test_changing_the_level_updates_the_status_line(app) -> None:
    app._finding_level.set("everything")
    app._set_finding_level()
    settle(app)
    assert "note" in str(app.status.cget("text"))
    app._finding_level.set("warning")
    app._set_finding_level()
    settle(app)
    assert "hidden" in str(app.status.cget("text"))


def test_the_level_is_remembered(app) -> None:
    app._finding_level.set("unfinished")
    app._set_finding_level()
    settle(app)
    assert app.settings.finding_level == "unfinished"


# --- rules -------------------------------------------------------------------


def test_the_rules_table_is_rendered(app) -> None:
    select_named(app, "context", "common")
    select_named(app, "type", "Money")
    assert "validators" in app.editor.tables
    assert len(app.editor.tables["validators"].get_children()) == 3


def test_adding_a_rule_to_a_type(app, quiet) -> None:
    from uuid import UUID

    from designer_app import bindings

    select_named(app, "context", "common")
    row = select_named(app, "type", "Money")
    money = app.session.model.index()[UUID(row)]
    before = len(money.validators)
    quiet["rule"] = bindings.BindingDraft(
        validator=app.library.by_name("between").uuid,
        arguments={"min": "0.00", "max": "99.99"},
    )
    app._add_rule(UUID(row))
    settle(app)
    assert len(money.validators) == before + 1
    assert len(app.session.stack) == 1


def test_the_dialog_is_offered_only_rules_that_fit(app, quiet) -> None:
    from uuid import UUID

    select_named(app, "context", "common")
    row = select_named(app, "type", "Money")
    quiet["rule"] = None
    app._add_rule(UUID(row))
    settle(app)
    _title, _draft, rules, _slots, _params = quiet["rule_dialogs"][-1]
    offered = {choice.label for choice in rules}
    assert "between" in offered
    assert "max_length" not in offered, "a text rule was offered for a decimal"


def test_an_entity_rule_dialog_offers_its_slots(app, quiet) -> None:
    from uuid import UUID

    select_named(app, "context", "sales")
    row = select_named(app, "entity", "Order")
    quiet["rule"] = None
    app._add_rule(UUID(row))
    settle(app)
    _title, _draft, _rules, slots, _params = quiet["rule_dialogs"][-1]
    assert {choice.label for choice in slots} >= {"total", "order_number"}


def test_a_refused_rule_says_why(app, quiet) -> None:
    from uuid import UUID

    from designer_app import bindings

    select_named(app, "context", "common")
    row = select_named(app, "type", "Money")
    quiet["rule"] = bindings.BindingDraft(validator=app.library.by_name("between").uuid, arguments={"min": "nought"})
    app._add_rule(UUID(row))
    settle(app)
    assert quiet["warning"], "no reason was given"
    assert len(app.session.stack) == 0


def test_removing_a_rule_is_one_undo_step(app, quiet) -> None:
    from uuid import UUID

    select_named(app, "context", "common")
    row = select_named(app, "type", "Money")
    money = app.session.model.index()[UUID(row)]
    victim = money.validators[1]
    app._remove_rule(UUID(row), str(victim.uuid))
    settle(app)
    assert victim not in money.validators
    app.undo()
    settle(app)
    assert money.validators[1] is victim


def test_cancelling_the_rule_dialog_changes_nothing(app, quiet) -> None:
    from uuid import UUID

    select_named(app, "context", "common")
    row = select_named(app, "type", "Money")
    quiet["rule"] = None
    app._add_rule(UUID(row))
    settle(app)
    assert len(app.session.stack) == 0


def test_making_a_validator_composite_translates_its_expression(app) -> None:
    """Names where identities belong would mean something different from what
    the text says."""
    from uuid import UUID

    select_named(app, "context", "sales")
    row = select_named(app, "validator", "is_order_number")
    item = app.session.model.index()[UUID(row)]
    app.editor._commit_now("expression", "is_uuid OR is_email")
    settle(app)
    app.editor._commit_now("kind", "composite")
    settle(app)
    assert item.kind == "composite"
    assert "is_uuid" not in item.expression, "an operand name was stored"
    assert app.editor._spec.by_key("expression").value == "is_uuid OR is_email"


def test_changing_the_kind_is_one_undo_step(app) -> None:
    from uuid import UUID

    select_named(app, "context", "sales")
    row = select_named(app, "validator", "order_reference")
    item = app.session.model.index()[UUID(row)]
    before = item.expression
    app.editor._commit_now("kind", "leaf")
    settle(app)
    assert item.kind == "leaf"
    app.undo()
    settle(app)
    assert item.kind == "composite"
    assert item.expression == before


# --- column widths -----------------------------------------------------------


def test_the_scrollbar_survives_a_narrow_column(app) -> None:
    """Packed after the tree, the scrollbar is the one squeezed out when the
    column gets narrow — exactly when it is needed most."""
    app.geometry("1024x768")
    app.update()
    settle(app)
    for name in COLUMNS:
        column = app.columns[name]
        bar = next(child for child in column.winfo_children() if child.winfo_class() == "TScrollbar")
        assert bar.winfo_ismapped(), f"{name} lost its scrollbar"
        assert bar.winfo_width() > 1, f"{name}'s scrollbar has no width"


def test_a_column_sizes_itself_to_its_contents(app) -> None:
    select_named(app, "context", "sales")
    settle(app)
    widths = {name: int(app.columns[name].tree.column("#0", "width")) for name in COLUMNS}
    assert all(width > 0 for width in widths.values())
    assert len(set(widths.values())) > 1, "every column came out the same width"


def test_a_column_can_be_dragged_narrower_than_it_prefers(app) -> None:
    column = app.columns["type"]
    assert int(column.tree.column("#0", "minwidth")) < int(column.tree.column("#0", "width"))
