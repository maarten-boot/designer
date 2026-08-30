"""One browser column.

A thin adapter over `rows`: it owns a filter entry, a Treeview and a small
toolbar, and knows nothing about what it is showing beyond the rows it is
handed. Every column is the same widget, which is why `Treeview` is used even
for the flat ones — one code path, and sortable headings for free.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .rows import ColumnData, Row, preferred_width
from .state import COLUMNS
from .tooltip import attach

# Row styling. Kept here rather than scattered through the code so the palette
# is one thing to change, and so the relationship colours stay distinguishable
# from the state ones.
TAG_STYLES: dict[str, dict[str, str]] = {
    "abstract": {"foreground": "#555555"},
    "builtin": {"foreground": "#777777"},
    "unnamed": {"foreground": "#999999"},
    "incomplete": {"foreground": "#8a6d00"},
    "context-only": {"foreground": "#aaaaaa"},
    "uses": {"background": "#e8f0fe"},
    "references": {"background": "#e6f4ea"},
    "contains": {"background": "#fdf1e3"},
}

# Several columns hold a selection at once, and only one of them is what the
# editor is showing. The active one is marked in amber; the others keep a muted
# grey, so a stale selection still reads as "chosen earlier" without competing
# with the current one.
ACTIVE_SELECTION = "#ffcf5c"
IDLE_SELECTION = "#d8d8d8"
SELECTED_TEXT = "#111111"

ACTIVE_STYLE = "Active.Treeview"
IDLE_STYLE = "Idle.Treeview"

KEEP = object()
"""Passed as `select` to mean "leave the widget's own selection alone".

Distinct from None, which means "clear it": choosing a context clears the other
columns, and falling back to the widget there would put a selection back that
the application has already dropped.
"""


def install_tree_styles(widget: tk.Misc) -> None:
    style = ttk.Style(widget)
    for name, colour in ((ACTIVE_STYLE, ACTIVE_SELECTION), (IDLE_STYLE, IDLE_SELECTION)):
        style.map(
            name,
            background=[("selected", colour)],
            foreground=[("selected", SELECTED_TEXT)],
        )


class ColumnView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        on_select: Callable[[str, str | None], None],
        on_sort: Callable[[str], None] | None = None,
        on_new: Callable[[str], None] | None = None,
        on_duplicate: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self._on_select = on_select
        self._filter = tk.StringVar()
        self._rows: dict[str, Row] = {}
        # what the application was last told. Repopulating the tree clears the
        # selection and then puts it back, so two events arrive for a selection
        # that never really changed; this is what tells them apart.
        self._reported: str | None = None

        header = ttk.Frame(self)
        header.pack(fill="x", padx=2, pady=(2, 0))
        # the heading is the sort control: a long list is worth reversing
        # rather than scrolling to the end of, and there is nowhere else
        # obvious to put it in a column with no table headings
        self._heading = ttk.Label(header, text=title, font=("TkDefaultFont", 9, "bold"))
        self._heading.pack(side="left")
        if on_sort is not None:
            self._heading.configure(cursor="hand2")
            self._heading.bind("<Button-1>", lambda _e: on_sort(title))
            attach(self._heading, "Click to reverse the order")

        # New, Duplicate and Delete sit on the column, not in the editor: a
        # button that appears and disappears inside the form makes the pane jump
        self._buttons: dict[str, ttk.Button] = {}
        for name, command, hint in (
            ("+", on_new, f"New {title.lower()}, empty, in the current context"),
            ("=", on_duplicate, f"Copy the selected {title.lower()}, without its name"),
            ("-", on_delete, f"Delete the selected {title.lower()}, after showing the impact"),
        ):
            if command is None:
                continue
            button = ttk.Button(header, text=name, width=2, command=lambda c=command: c(title))
            button.pack(side="right")
            attach(button, hint)
            self._buttons[name] = button

        entry = ttk.Entry(self, textvariable=self._filter)
        entry.pack(fill="x", padx=2, pady=2)
        attach(entry, f"Show only {title.lower()}s whose name contains this")
        self._filter.trace_add("write", lambda *_: self.event_generate("<<FilterChanged>>"))

        install_tree_styles(self)
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse", style=IDLE_STYLE)
        self._active = False
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        # the scrollbar is packed first. Packed after the tree it is the one
        # squeezed out when the column gets narrow, which is exactly when it is
        # needed most.
        scroll.pack(side="right", fill="y", pady=(0, 2))
        self.tree.pack(side="left", fill="both", expand=True, padx=(2, 0), pady=(0, 2))

        for tag, style in TAG_STYLES.items():
            self.tree.tag_configure(tag, **style)

        self.tree.bind("<<TreeviewSelect>>", self._selected)
        # A click on the row that is already selected changes nothing in the
        # widget, so no select event fires — but the user has just chosen this
        # column, and the editor has to follow. Only a real click does this, so
        # it cannot restart the rebuild loop that the dedupe above prevents.
        self.tree.bind("<ButtonRelease-1>", self._clicked)
        self._set_delete_enabled(False)

    # --- content ------------------------------------------------------------

    @property
    def filter_text(self) -> str:
        return self._filter.get()

    def show(
        self,
        data: ColumnData,
        extra_tags: dict[str, tuple[str, ...]] | None = None,
        reveal: object = None,
        select: object = KEEP,
    ) -> None:
        """Replace the contents, keeping the selection if it survived.

        `reveal` scrolls one row into view. Highlighting says which rows are
        related; it says nothing at all if the row is below the fold.

        `select` is what the application believes is selected here, which is
        not always what the widget shows — a selection set in code, such as the
        context chosen at startup, has to be reflected back or the row looks
        unchosen.
        """
        told = select is not KEEP
        selected = (str(select) if select is not None else None) if told else self.selected_id
        self.tree.delete(*self.tree.get_children())
        self._rows = {row.id: row for row in data.rows}
        extra = extra_tags or {}
        for row in data.rows:
            parent = row.parent if row.parent in self._rows else ""
            self.tree.insert(
                parent,
                "end",
                iid=row.id,
                text=row.label,
                tags=row.tags + extra.get(row.id, ()),
                open=True,
            )
        if selected and selected in self._rows:
            self.tree.selection_set(selected)
            if told:
                self._reported = selected
        else:
            if told:
                self.tree.selection_remove(*self.tree.selection())
            # the row is gone, so the application has to hear about it
            self._reported = None
        self.fit_to_contents()
        if reveal is not None and str(reveal) in self._rows:
            self.tree.see(str(reveal))
        self._set_delete_enabled(bool(self.selected_id))

    def set_sort(self, descending: bool) -> None:
        """Show which way the column runs."""
        arrow = "\u25be" if descending else "\u25b4"
        self._heading.configure(text=f"{self.title} {arrow}")

    def set_active(self, active: bool) -> None:
        """Mark this column as the one the editor is showing."""
        if active == self._active:
            return
        self._active = active
        self.tree.configure(style=ACTIVE_STYLE if active else IDLE_STYLE)

    @property
    def selected_id(self) -> str | None:
        chosen = self.tree.selection()
        return chosen[0] if chosen else None

    @property
    def selected_row(self) -> Row | None:
        chosen = self.selected_id
        return self._rows.get(chosen) if chosen else None

    def _selected(self, _event: object) -> None:
        """Report only a selection that actually changed.

        `<<TreeviewSelect>>` is queued, not delivered inline, so by the time
        this runs the tree has settled — reading the *current* selection rather
        than trusting the event's ordering is what makes the check work. It has
        to: `show` empties the tree and refills it, and the pair of events that
        produces would otherwise drive refresh and show round the event queue
        forever. A hang, not a failure.
        """
        current = self.selected_id
        self._set_delete_enabled(bool(current))
        if current == self._reported:
            return
        self._reported = current
        self._on_select(self.title, current)

    def _clicked(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if row and row == self._reported:
            self._on_select(self.title, row)

    def _set_delete_enabled(self, enabled: bool) -> None:
        """Disabled rather than hidden: a control that comes and goes is harder
        to aim at than one that greys out."""
        button = self._buttons.get("-")
        if button is not None:
            button.state(["!disabled"] if enabled else ["disabled"])

    # --- sizing -------------------------------------------------------------

    def fit_to_contents(self) -> None:
        """Size the column to what is actually in it.

        The preferred width comes from the rows; the minimum is much smaller,
        so six columns still fit on a small screen and a column can be dragged
        narrow when its neighbour matters more.
        """
        from tkinter import font

        measure = font.nametofont("TkDefaultFont")
        em = measure.measure("m")
        indent = 24  # the disclosure triangle and its inset
        widths = [measure.measure(row.label) + indent * (1 if row.parent else 0) for row in self._rows.values()]
        wanted = preferred_width(widths, em, columns=len(COLUMNS))
        # the same number for both: a width the column cannot be given down to
        # is a minimum, and having two of them meant the flat floor quietly
        # replaced the calculation
        self.tree.column("#0", width=wanted, minwidth=wanted, stretch=True)
