"""The editor pane.

A renderer for a `FormSpec`, and nothing more: it knows about entries and
comboboxes, not about Types or Schemas. Everything that decides *what* to show
lives in `forms`, where it can be tested without a display.

The editor is live. There is no Apply: a structured control commits the moment
it changes, and a text field commits when it loses focus or takes Enter. That
follows from one user action being one undo step — an Apply button would either
bundle a form's worth of edits into one step or push several at once, and
neither is what Ctrl-Z should mean.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from tkinter import ttk
from uuid import UUID

from .columns import TAG_STYLES
from .forms import NONE_CHOICE, Action, Field, FormSpec
from .rows import next_sort, sorted_rows

# The form sits on its own near-white panel rather than the theme's grey. Notes
# and findings are secondary text, and secondary text on a grey background is
# the first thing to become unreadable — this gives it something to sit on.
PANEL = "#fcfcfc"
FINDING_COLOUR = "#a01b0b"
ATTENTION_COLOUR = "#a35a00"
NOTE_COLOUR = "#4f4f4f"
READONLY_COLOUR = "#3c3c3c"

FRAME_STYLE = "Form.TFrame"
LABEL_STYLE = "Form.TLabel"
NOTE_STYLE = "FormNote.TLabel"
FINDING_STYLE = "FormFinding.TLabel"
READONLY_STYLE = "FormReadonly.TLabel"
ATTENTION_STYLE = "FormAttention.TLabel"
READONLY_ENTRY = "FormReadonly.TEntry"
ATTENTION_ENTRY = "FormAttention.TEntry"
TITLE_STYLE = "FormTitle.TLabel"


def install_styles(widget: tk.Misc) -> None:
    """Define the form's styles once, on the widget's own style object."""
    style = ttk.Style(widget)
    style.configure(FRAME_STYLE, background=PANEL)
    style.configure(LABEL_STYLE, background=PANEL)
    style.configure(TITLE_STYLE, background=PANEL, font=("TkDefaultFont", 10, "bold"))
    style.configure(NOTE_STYLE, background=PANEL, foreground=NOTE_COLOUR)
    style.configure(FINDING_STYLE, background=PANEL, foreground=FINDING_COLOUR)
    style.configure(READONLY_STYLE, background=PANEL, foreground=READONLY_COLOUR)
    # amber, not red: true and worth noticing, but not a fault
    style.configure(
        ATTENTION_STYLE,
        background=PANEL,
        foreground=ATTENTION_COLOUR,
        font=("TkDefaultFont", 9, "bold"),
    )
    # entries rather than labels for read-only values, so the text can be
    # selected and copied; flat and unbordered so they still read as values
    for name, colour in ((READONLY_ENTRY, READONLY_COLOUR), (ATTENTION_ENTRY, ATTENTION_COLOUR)):
        style.configure(
            name,
            foreground=colour,
            fieldbackground=PANEL,
            background=PANEL,
            borderwidth=0,
            relief="flat",
        )
        style.map(name, fieldbackground=[("readonly", PANEL)], foreground=[("readonly", colour)])


@dataclass
class _Table:
    """What a rendered table needs to remember to be sortable."""

    tree: ttk.Treeview
    columns: tuple[str, ...] = ()
    stored: list[str] = field(default_factory=list)
    buttons: list = field(default_factory=list)
    update_enabled: Callable[[], None] = lambda: None
    column: int = -1
    direction: int = 0
    """0 stored order, 1 ascending, 2 descending."""


class FormView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        on_commit: Callable[[UUID, str, object], None],
        on_action: Callable[[UUID, str, str, str | None], None] | None = None,
    ) -> None:
        super().__init__(parent, style=FRAME_STYLE, padding=6)
        install_styles(self)
        self._on_commit = on_commit
        self._on_action = on_action or (lambda *_: None)
        self.tables: dict[str, ttk.Treeview] = {}
        self._table_state: dict[str, _Table] = {}
        self._spec: FormSpec | None = None
        self._widgets: dict[str, tk.Misc] = {}
        # Tk holds a variable by its Tcl name, not by a Python reference. A
        # StringVar left as a local is collected, its Tcl variable goes with
        # it, and the entry then reports an empty string — which commits as a
        # cleared field. Keeping them here is what stops that.
        self._variables: dict[str, tk.Variable] = {}
        self._committed: dict[str, str] = {}
        self.columnconfigure(1, weight=1)

    # --- rendering ----------------------------------------------------------

    def clear(self, message: str = "") -> None:
        # forget first, then destroy. Destroying a widget that has focus fires
        # <FocusOut> into a handler whose form is half torn down, and that
        # handler used to read an empty value from the dying widget and commit
        # it — blanking the name of whatever happened to be selected.
        self._spec, self._widgets, self._committed = None, {}, {}
        self._variables = {}
        self.tables = {}
        for child in self.winfo_children():
            child.destroy()
        if message:
            ttk.Label(self, text=message, style=NOTE_STYLE, justify="left").grid(
                row=0, column=0, sticky="nw", padx=4, pady=4
            )

    def show(self, spec: FormSpec) -> None:
        self.clear()
        self._spec = spec
        title = f"{spec.kind}: {spec.title}"
        if spec.read_only:
            title += "   (read only)"
        ttk.Label(self, text=title, style=TITLE_STYLE).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 6)
        )
        row = 1
        if spec.note:
            ttk.Label(self, text=spec.note, style=NOTE_STYLE, wraplength=520, justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 6)
            )
            row += 1
        if spec.actions:
            buttons = ttk.Frame(self, style=FRAME_STYLE)
            buttons.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 8))
            for action in spec.actions:
                button = ttk.Button(buttons, text=action.label, command=lambda a=action: self._fire("", a.name))
                button.pack(side="left", padx=(0, 4))
                if not action.enabled:
                    button.state(["disabled"])
            row += 1
        for entry in spec.fields:
            row = self._render(entry, row)

    def _render(self, entry: Field, row: int) -> int:
        ttk.Label(self, text=entry.label, style=LABEL_STYLE).grid(row=row, column=0, sticky="nw", padx=(4, 8), pady=2)
        builder = {
            "readonly": self._readonly,
            "text": self._text,
            "multiline": self._multiline,
            "checkbox": self._checkbox,
            "choice": self._choice,
            "summary": self._summary,
            "table": self._table,
        }[entry.kind]
        builder(entry, row)
        row += 1
        # notes and findings are prose about the model, and prose is what gets
        # quoted back in feedback — a label cannot be selected, so these are
        # read-only text rather than labels
        for message in entry.findings:
            self._prose(message, FINDING_COLOUR, row)
            row += 1
        if entry.note:
            self._prose(entry.note, NOTE_COLOUR, row)
            row += 1
        return row

    # --- field kinds --------------------------------------------------------

    def _prose(self, message: str, colour: str, row: int) -> None:
        """A line of explanation, selectable so it can be quoted."""
        widget = tk.Text(
            self,
            height=max(1, (len(message) // 78) + 1),
            wrap="word",
            width=78,
            background=PANEL,
            foreground=colour,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        widget.insert("1.0", message)
        widget.bind("<Key>", lambda event: None if event.state & 4 else "break")
        widget.grid(row=row, column=1, sticky="w", padx=4)

    def _readonly(self, entry: Field, row: int) -> None:
        """A read-only value you can still select and copy.

        A label cannot be selected, so a uuid, a picture or a resolved path
        could only be retyped or screenshotted. An entry in readonly state
        looks the same and behaves like text.
        """
        variable = tk.StringVar(value=str(entry.value))
        self._variables[f"readonly:{entry.key}"] = variable
        ttk.Entry(
            self,
            textvariable=variable,
            state="readonly",
            style=ATTENTION_ENTRY if entry.emphasis == "attention" else READONLY_ENTRY,
            width=max(12, min(60, len(str(entry.value)) + 2)),
        ).grid(row=row, column=1, sticky="w", padx=4, pady=2)

    def _summary(self, entry: Field, row: int) -> None:
        """Several lines, selectable, not editable.

        A Text in `disabled` state cannot be selected either, so it is left
        editable and every key is refused instead — selection and copying still
        work, typing does nothing.
        """
        lines = [str(line) for line in (entry.value if isinstance(entry.value, list) else [entry.value])]
        widget = tk.Text(
            self,
            height=min(10, max(1, len(lines))),
            wrap="none",
            background=PANEL,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            foreground=ATTENTION_COLOUR if entry.emphasis == "attention" else "#000000",
            width=max(20, min(70, max((len(line) for line in lines), default=20) + 2)),
        )
        widget.insert("1.0", "\n".join(lines))
        widget.bind("<Key>", lambda event: None if event.state & 4 else "break")
        widget.grid(row=row, column=1, sticky="w", padx=4, pady=2)

    def _table(self, entry: Field, row: int) -> None:
        """A list with buttons.

        What the rows are, and which buttons apply, is decided in `forms`; this
        only draws it. Buttons that act on a selection are disabled rather than
        hidden while nothing is selected.
        """
        holder = ttk.Frame(self, style=FRAME_STYLE)
        holder.grid(row=row, column=1, sticky="ew", padx=4, pady=2)

        tree = ttk.Treeview(
            holder,
            columns=[f"c{i}" for i in range(len(entry.columns))],
            show="headings",
            height=min(8, max(3, len(entry.rows))),
            selectmode="browse",
        )
        for index, heading in enumerate(entry.columns):
            tree.heading(
                f"c{index}",
                text=heading,
                command=lambda k=entry.key, c=index: self._sort_table(k, c),
            )
            tree.column(f"c{index}", width=140, stretch=True)
        tags_of = {r.id: r.tags for r in entry.rows}
        for table_row in entry.rows:
            tree.insert("", "end", iid=table_row.id, values=table_row.cells, tags=table_row.tags)
        for tag, style in TAG_STYLES.items():
            tree.tag_configure(tag, **style)
        tree.pack(side="top", fill="x")
        self.tables[entry.key] = tree

        buttons = ttk.Frame(holder, style=FRAME_STYLE)
        buttons.pack(side="top", anchor="w", pady=(2, 0))
        widgets: list[tuple[ttk.Button, Action]] = []
        for action in entry.actions:
            button = ttk.Button(
                buttons,
                text=action.label,
                command=lambda a=action, k=entry.key: self._fire(k, a.name),
            )
            button.pack(side="left", padx=(0, 4))
            widgets.append((button, action))

        def update_enabled(_event: object = None) -> None:
            chosen = tree.selection()
            row = chosen[0] if chosen else None
            tags = tags_of.get(row, ()) if row else ()
            existing = self._table_state.get(entry.key)
            sorted_now = bool(existing.direction) if existing else False
            for button, action in widgets:
                allowed = action.enabled and (row is not None or not action.needs_row)
                if allowed and action.name.startswith("move_"):
                    # the stored order is what these change, and it is not what
                    # is on screen while a sort is applied
                    allowed = not sorted_now
                if allowed and action.requires == "own":
                    # an inherited slot is edited on the entity that declares it
                    allowed = "inherited" not in tags
                if allowed and action.requires == "inherited":
                    # overriding a slot the entity already declares is meaningless
                    allowed = "inherited" in tags
                button.state(["!disabled"] if allowed else ["disabled"])

        tree.bind("<<TreeviewSelect>>", update_enabled)
        self._table_state[entry.key] = _Table(tree, entry.columns, [r.id for r in entry.rows], widgets, update_enabled)
        update_enabled()

    def _sort_table(self, key: str, column: int) -> None:
        """Sort a table for reading, without pretending the order changed.

        Stored order is meaningful in the slots table — it is the column order
        of the generated table, and Up and Down are how it is set. So a sort is
        a *view*: while one is active, the buttons that reorder rows are
        disabled, because a control that moves a row somewhere the eye cannot
        follow is worse than no control. Clicking the same heading a third time
        returns to stored order and gives them back.
        """
        state = self._table_state.get(key)
        if state is None:
            return
        state.column, state.direction = next_sort(column, state.column, state.direction)
        order = sorted_rows(
            state.stored,
            {row: str(state.tree.set(row, f"c{column}")) for row in state.stored},
            state.direction,
        )
        for position, row in enumerate(order):
            state.tree.move(row, "", position)
        for index, heading in enumerate(state.columns):
            arrow = "" if index != state.column else (" \u25b2", " \u25bc")[state.direction - 1]
            state.tree.heading(f"c{index}", text=f"{heading}{arrow}")
        state.update_enabled()

    def _text(self, entry: Field, row: int) -> None:
        variable = tk.StringVar(value=str(entry.value or ""))
        self._variables[entry.key] = variable
        widget = ttk.Entry(self, textvariable=variable)
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        self._track(entry.key, widget, variable)

    def _multiline(self, entry: Field, row: int) -> None:
        # undo=False: one undo stack for the whole application. Ctrl-Z means the
        # same thing everywhere, which is worth more than character-level undo
        # inside one field. Escape puts the field back instead.
        widget = tk.Text(
            self,
            height=4,
            wrap="word",
            undo=False,
            background="#ffffff",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        widget.insert("1.0", str(entry.value or ""))
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        self._committed[entry.key] = str(entry.value or "")
        self._widgets[entry.key] = widget
        widget.bind("<FocusOut>", lambda _e, k=entry.key: self._commit_text(k))
        widget.bind("<Escape>", lambda _e, k=entry.key: self._revert(k))
        widget.bind("<Control-Return>", lambda _e, k=entry.key: self._commit_text(k))

    def _checkbox(self, entry: Field, row: int) -> None:
        variable = tk.BooleanVar(value=bool(entry.value))
        self._variables[entry.key] = variable
        widget = ttk.Checkbutton(
            self,
            variable=variable,
            command=lambda k=entry.key, v=variable: self._commit_now(k, v.get()),
        )
        widget.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        self._widgets[entry.key] = widget

    def _choice(self, entry: Field, row: int) -> None:
        labels = [c.label for c in entry.choices]
        by_label = {c.label: c.id for c in entry.choices}
        current = next((c.label for c in entry.choices if c.id == entry.value), NONE_CHOICE)
        variable = tk.StringVar(value=current)
        self._variables[entry.key] = variable
        widget = ttk.Combobox(self, textvariable=variable, values=labels, state="readonly")
        widget.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        widget.bind(
            "<<ComboboxSelected>>",
            lambda _e, k=entry.key, v=variable: self._commit_now(k, by_label.get(v.get())),
        )
        self._widgets[entry.key] = widget

    # --- committing ---------------------------------------------------------

    def _track(self, key: str, widget: ttk.Entry, variable: tk.StringVar) -> None:
        self._widgets[key] = widget
        self._committed[key] = variable.get()
        widget.bind("<FocusOut>", lambda _e, k=key: self._commit_text(k))
        widget.bind("<Return>", lambda _e, k=key: self._commit_text(k))
        widget.bind("<Escape>", lambda _e, k=key: self._revert(k))

    def value_of(self, key: str) -> str:
        """What the field holds, or what it last committed.

        Never an empty string for a widget that is gone: an absent widget is
        not a cleared field, and treating it as one is how a name got blanked.
        """
        widget = self._widgets.get(key)
        fallback = self._committed.get(key, "")
        if widget is None:
            return fallback
        try:
            if not widget.winfo_exists():
                return fallback
            if isinstance(widget, tk.Text):
                return widget.get("1.0", "end-1c")
            if isinstance(widget, ttk.Entry):
                return widget.get()
        except tk.TclError:
            return fallback
        return fallback

    def _commit_text(self, key: str) -> None:
        """Commit only a real change, and only to the item this form is for.

        Focus moves whenever the form is rebuilt, so committing unconditionally
        would push a command for every click — and committing against the
        current selection rather than the form's own item would apply an edit
        to whatever was clicked next.
        """
        if self._spec is None or key not in self._committed:
            return
        value = self.value_of(key)
        if value == self._committed.get(key):
            return
        self._committed[key] = value
        self._on_commit(self._spec.uuid, key, value)

    def selected_in(self, key: str) -> str | None:
        tree = self.tables.get(key)
        chosen = tree.selection() if tree is not None else ()
        return chosen[0] if chosen else None

    def _fire(self, key: str, action: str) -> None:
        """A table button was pressed, against this form's item."""
        if self._spec is None:
            return
        self._on_action(self._spec.uuid, key, action, self.selected_in(key))

    def _commit_now(self, key: str, value: object) -> None:
        """A structured control changed, so commit against this form's item."""
        if self._spec is None:
            return
        self._on_commit(self._spec.uuid, key, value)

    def _revert(self, key: str) -> None:
        """Escape puts the field back to its last committed value.

        This is what replaces in-field undo, and without it a mistyped
        expression could only be fixed by retyping it.
        """
        widget = self._widgets.get(key)
        previous = self._committed.get(key, "")
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", previous)
        elif isinstance(widget, ttk.Entry):
            widget.delete(0, "end")
            widget.insert(0, previous)

    def commit_pending(self) -> None:
        """Flush any field the user typed in but did not leave.

        Called before the selection changes, so an edit is never lost simply
        because the next click landed elsewhere.
        """
        for key in list(self._committed):
            self._commit_text(key)
