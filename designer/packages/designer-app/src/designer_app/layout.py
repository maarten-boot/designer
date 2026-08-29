"""Collapsing columns.

Manual only. Automatic collapse was deferred, and that removed more than the
feature: pinning existed solely to stop an automatic rule overriding an explicit
choice, so with no automatic rule a collapsed column is simply collapsed. The
resize monitoring, the debounce and the priority order went with it.

`forget` and `insert` rather than driving a sash to zero — a zero-width pane
leaves a dead draggable strip that fights the next resize.

The tkinter import is optional on purpose. Everything here is arithmetic over
which columns are showing, and being able to exercise it against a stub rather
than a live window is worth a three-line shim — the alternative is a module that
can only be tested on a machine with a display, which is how the off-by-one in
`restore` reached a user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

try:  # pragma: no cover - exercised by whichever branch the platform takes
    from tkinter import TclError
except ImportError:  # pragma: no cover

    class TclError(Exception):  # type: ignore[no-redef]
        """Stand-in so this module imports without a display."""


class PanedLike(Protocol):
    """The four calls this needs from a `ttk.PanedWindow`."""

    def panes(self) -> tuple[Any, ...]: ...
    def add(self, child: Any, **kwargs: Any) -> None: ...
    def insert(self, pos: Any, child: Any, **kwargs: Any) -> None: ...
    def forget(self, child: Any) -> None: ...


@dataclass
class CollapseManager:
    paned: PanedLike
    order: list[str]
    panes: dict[str, Any]
    widths: dict[str, int] = field(default_factory=dict)
    collapsed: set[str] = field(default_factory=set)
    weight: int = 1

    def is_collapsed(self, name: str) -> bool:
        return name in self.collapsed

    def toggle(self, name: str) -> bool:
        if name in self.collapsed:
            self.restore(name)
        else:
            self.collapse(name)
        return name in self.collapsed

    def collapse(self, name: str) -> None:
        if name in self.collapsed or name not in self.panes:
            return
        pane = self.panes[name]
        try:
            width = pane.winfo_width()
        except (TclError, AttributeError):
            width = 0
        if width > 1:  # an unmapped pane reports 1, which is not a width
            self.widths[name] = width
        else:
            self.widths.pop(name, None)
        self.paned.forget(pane)
        self.collapsed.add(name)

    def restore(self, name: str) -> None:
        """Put the pane back where it was, not at the end.

        `insert` needs a position *before* an existing pane, so restoring the
        rightmost column has to `add` instead: with five panes showing, index
        five is out of bounds rather than meaning "after the last".
        """
        if name not in self.collapsed or name not in self.panes:
            return
        position = insertion_index(self.order, self.collapsed, name)
        pane = self.panes[name]
        if position >= len(self.paned.panes()):
            self.paned.add(pane, weight=self.weight)
        else:
            self.paned.insert(position, pane, weight=self.weight)
        self.collapsed.discard(name)

    def reset(self) -> None:
        """Every column back, at default widths.

        Widths are cleared first: restoring and *then* clearing would leave the
        remembered sizes to be applied anyway, which is not a reset.
        """
        self.widths.clear()
        for name in self.order:  # left to right, so each position stays valid
            self.restore(name)

    def state(self) -> tuple[list[str], dict[str, int]]:
        return sorted(self.collapsed), dict(self.widths)


def visible_order(order: list[str], collapsed: set[str]) -> list[str]:
    return [name for name in order if name not in collapsed]


def insertion_index(order: list[str], collapsed: set[str], name: str) -> int:
    """Where a restored column belongs among those currently showing."""
    return sum(1 for other in order[: order.index(name)] if other not in collapsed)
