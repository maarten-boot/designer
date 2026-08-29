"""Collapsing columns.

Exercised against a stub that behaves like `ttk.PanedWindow` in the one way that
matters: `insert` takes a position *before* an existing pane, so an index equal
to the number of panes is out of bounds rather than meaning "append". That is
the rule the first version of `restore` broke, and it could not be caught here
until this module stopped needing a display.
"""

from __future__ import annotations

import pytest

from designer_app.layout import CollapseManager, insertion_index, visible_order
from designer_app.state import COLUMNS


class Pane:
    def __init__(self, name: str) -> None:
        self.name = name
        self.width = 200

    def winfo_width(self) -> int:
        return self.width

    def __repr__(self) -> str:
        return f"<{self.name}>"


class FakePaned:
    """As strict as the real widget about insert positions."""

    def __init__(self, children: list[Pane]) -> None:
        self._children = list(children)
        self.calls: list[str] = []

    def panes(self) -> tuple[Pane, ...]:
        return tuple(self._children)

    def add(self, child: Pane, **_kwargs: object) -> None:
        self.calls.append(f"add {child.name}")
        self._children.append(child)

    def insert(self, pos: int, child: Pane, **_kwargs: object) -> None:
        if not isinstance(pos, int) or pos >= len(self._children):
            raise IndexError(f"Slave index {pos} out of bounds")
        self.calls.append(f"insert {pos} {child.name}")
        self._children.insert(pos, child)

    def forget(self, child: Pane) -> None:
        self.calls.append(f"forget {child.name}")
        self._children.remove(child)

    def names(self) -> list[str]:
        return [c.name for c in self._children]


@pytest.fixture
def manager():
    panes = {name: Pane(name) for name in COLUMNS}
    paned = FakePaned(list(panes.values()))
    return CollapseManager(paned, list(COLUMNS), panes)


# --- the reported failure ---------------------------------------------------


def test_restoring_the_rightmost_column(manager) -> None:
    """The crash: with five panes showing, inserting at index five is out of
    bounds. The last column has to be added, not inserted."""
    last = COLUMNS[-1]
    manager.collapse(last)
    manager.restore(last)
    assert manager.paned.names() == list(COLUMNS)


def test_reset_after_collapsing_the_last_column(manager) -> None:
    """The exact path from the traceback."""
    manager.collapse(COLUMNS[-1])
    manager.reset()
    assert manager.paned.names() == list(COLUMNS)
    assert manager.collapsed == set()


def test_reset_with_every_column_collapsed(manager) -> None:
    for name in COLUMNS:
        manager.collapse(name)
    assert manager.paned.names() == []
    manager.reset()
    assert manager.paned.names() == list(COLUMNS)


def test_reset_with_nothing_collapsed_is_a_no_op(manager) -> None:
    manager.reset()
    assert manager.paned.names() == list(COLUMNS)
    assert manager.paned.calls == []


# --- ordering ---------------------------------------------------------------


@pytest.mark.parametrize("name", COLUMNS)
def test_any_single_column_round_trips_to_its_own_place(manager, name) -> None:
    manager.collapse(name)
    manager.restore(name)
    assert manager.paned.names() == list(COLUMNS)


def test_restoring_the_first_column_does_not_put_it_last(manager) -> None:
    first = COLUMNS[0]
    manager.collapse(first)
    manager.restore(first)
    assert manager.paned.names()[0] == first


def test_restoring_out_of_order_still_lands_correctly(manager) -> None:
    manager.collapse(COLUMNS[1])
    manager.collapse(COLUMNS[3])
    manager.collapse(COLUMNS[5])
    manager.restore(COLUMNS[5])
    manager.restore(COLUMNS[1])
    manager.restore(COLUMNS[3])
    assert manager.paned.names() == list(COLUMNS)


def test_toggle_reports_the_resulting_state(manager) -> None:
    name = COLUMNS[2]
    assert manager.toggle(name) is True
    assert manager.is_collapsed(name)
    assert manager.toggle(name) is False
    assert not manager.is_collapsed(name)


# --- widths -----------------------------------------------------------------


def test_a_collapsed_width_is_remembered(manager) -> None:
    name = COLUMNS[2]
    manager.panes[name].width = 321
    manager.collapse(name)
    assert manager.widths[name] == 321


def test_an_unmapped_pane_reports_no_useful_width(manager) -> None:
    """tk reports 1 for a pane that has never been drawn; storing that would
    restore the column as a sliver."""
    name = COLUMNS[2]
    manager.panes[name].width = 1
    manager.collapse(name)
    assert name not in manager.widths


def test_reset_forgets_remembered_widths(manager) -> None:
    name = COLUMNS[2]
    manager.panes[name].width = 321
    manager.collapse(name)
    manager.reset()
    assert manager.widths == {}


def test_state_is_what_the_settings_file_stores(manager) -> None:
    manager.panes[COLUMNS[1]].width = 250
    manager.collapse(COLUMNS[1])
    collapsed, widths = manager.state()
    assert collapsed == [COLUMNS[1]]
    assert widths == {COLUMNS[1]: 250}


# --- the pure helpers -------------------------------------------------------


def test_insertion_index_counts_only_visible_columns() -> None:
    order = list(COLUMNS)
    assert insertion_index(order, set(), order[0]) == 0
    assert insertion_index(order, set(), order[3]) == 3
    assert insertion_index(order, {order[0], order[1]}, order[3]) == 1


def test_visible_order_keeps_the_left_to_right_sequence() -> None:
    order = list(COLUMNS)
    assert visible_order(order, {order[2]}) == [n for n in order if n != order[2]]


def test_collapsing_twice_changes_nothing(manager) -> None:
    name = COLUMNS[2]
    manager.collapse(name)
    manager.collapse(name)
    assert manager.paned.names().count(name) == 0
    assert manager.collapsed == {name}


def test_restoring_something_never_collapsed_changes_nothing(manager) -> None:
    manager.restore(COLUMNS[2])
    assert manager.paned.names() == list(COLUMNS)
