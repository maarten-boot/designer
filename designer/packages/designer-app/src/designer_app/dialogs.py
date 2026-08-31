"""Modal helpers.

Two dialogs, kept apart from the window that opens them so the decisions they
present — which entities may be chosen, what an addition would pull in — stay in
modules that do not need a display.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Chooser(tk.Toplevel):
    """Pick one thing from a list."""

    def __init__(self, parent: tk.Misc, title: str, prompt: str, options: list[tuple[str, str]]):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.result: str | None = None

        ttk.Label(self, text=prompt, wraplength=380, justify="left").pack(anchor="w", padx=10, pady=(10, 4))

        self._tree = ttk.Treeview(self, show="tree", selectmode="browse", height=12)
        for identifier, label in options:
            self._tree.insert("", "end", iid=identifier, text=label)
        self._tree.pack(fill="both", expand=True, padx=10)
        self._tree.bind("<Double-1>", lambda _e: self._accept())

        buttons = ttk.Frame(self)
        buttons.pack(anchor="e", padx=10, pady=10)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add", command=self._accept).pack(side="right", padx=(0, 6))

        if options:
            self._tree.selection_set(options[0][0])
        self._tree.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._accept())

    def _accept(self) -> None:
        chosen = self._tree.selection()
        self.result = chosen[0] if chosen else None
        self.destroy()

    def ask(self) -> str | None:
        """Show, wait, and return what was chosen."""
        self.grab_set()
        self.wait_window(self)
        return self.result


class FindingsWindow(tk.Toplevel):
    """Every finding, in a list you can act on.

    Not modal: it is something to work alongside, and double-clicking a row
    takes the selection to what the finding is about, which is the whole reason
    to show it rather than a count.
    """

    def __init__(self, parent: tk.Misc, rows, on_open) -> None:
        super().__init__(parent)
        self.title("Model findings")
        self.geometry("900x420")
        self._on_open = on_open

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        self._summary = ttk.Label(top, text="")
        self._summary.pack(side="left")
        ttk.Label(top, text="double-click a finding to go to it", foreground="#4f4f4f").pack(side="right")

        holder = ttk.Frame(self, padding=(10, 0, 10, 10))
        holder.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            holder,
            columns=("severity", "code", "where", "message"),
            show="headings",
            selectmode="browse",
        )
        for name, heading, width in (
            ("severity", "", 90),
            ("code", "Code", 80),
            ("where", "Item", 240),
            ("message", "What it says", 460),
        ):
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, stretch=(name == "message"))
        self._headings = ("Severity", "Code", "Item", "What it says")
        bar = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # a treeview cannot be selected as text, and a finding is exactly the
        # thing somebody wants to paste into a message
        self.tree.bind("<Control-c>", lambda _e: self.copy(selected_only=True))
        buttons = ttk.Frame(self, padding=(12, 0, 12, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Copy all", command=self.copy).pack(side="right")
        ttk.Button(buttons, text="Copy selected", command=lambda: self.copy(selected_only=True)).pack(
            side="right", padx=(0, 6)
        )

        self.tree.tag_configure("error", foreground="#a01b0b")
        self.tree.tag_configure("warning", foreground="#a35a00")
        self.tree.tag_configure("unfinished", foreground="#4f4f4f")
        self.tree.tag_configure("note", foreground="#4f4f4f")

        self.tree.bind("<Double-1>", self._open)
        self.tree.bind("<Return>", self._open)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.show(rows, "")

    def as_text(self, selected_only: bool = False) -> str:
        """The findings as tab-separated lines, headings included.

        Tabs rather than spaces: it pastes into a message as readable columns
        and into a spreadsheet as columns proper.
        """
        wanted = self.tree.selection() if selected_only else self.tree.get_children()
        lines = ["\t".join(self._headings)]
        lines += ["\t".join(str(v) for v in self.tree.item(row, "values")) for row in wanted]
        return "\n".join(lines)

    def copy(self, selected_only: bool = False) -> str:
        text = self.as_text(selected_only)
        self.clipboard_clear()
        self.clipboard_append(text)
        return text

    def show(self, rows, headline: str) -> None:
        self._rows = {row.id: row for row in rows}
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", iid=row.id, values=row.cells, tags=(row.marker,))
        self._summary.configure(text=headline or ("nothing to report" if not rows else f"{len(rows)} findings"))

    def _open(self, _event: object = None) -> None:
        chosen = self.tree.selection()
        if chosen and chosen[0] in self._rows:
            self._on_open(self._rows[chosen[0]])


class PathPicker(ttk.Frame):
    """Build a route one step at a time.

    Only steps that keep the path legal are offered, so an invalid path cannot
    be built: references that would leave the Schema are absent, references
    disappear at the length limit, and a value slot ends the walk. That is the
    difference between a control that guides and one that grades.
    """

    def __init__(self, parent: tk.Misc, label: str, path, steps_for, render, on_change) -> None:
        super().__init__(parent)
        self._path = tuple(path)
        self._steps_for = steps_for
        self._render = render
        self._on_change = on_change

        ttk.Label(self, text=label).grid(row=0, column=0, sticky="w")
        self._route = ttk.Label(self, text="", foreground="#3c3c3c")
        self._route.grid(row=0, column=1, sticky="w", padx=(8, 0))

        controls = ttk.Frame(self)
        controls.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(2, 6))
        self._choice = tk.StringVar()
        self._next = ttk.Combobox(controls, textvariable=self._choice, state="readonly", width=28)
        self._next.pack(side="left")
        self._next.bind("<<ComboboxSelected>>", lambda _e: self._take())
        self._back = ttk.Button(controls, text="Back", width=6, command=self._drop)
        self._back.pack(side="left", padx=(4, 0))
        self.columnconfigure(1, weight=1)
        self.refresh()

    @property
    def path(self) -> tuple:
        return self._path

    def refresh(self) -> None:
        steps = self._steps_for(self._path)
        self._labels = {f"{step.name}  \u2192 {step.reaches}" if step.continues else step.name: step for step in steps}
        self._next.configure(values=list(self._labels))
        self._choice.set("")
        self._route.configure(text=self._render(self._path))
        self._next.state(["!disabled"] if steps else ["disabled"])
        self._back.state(["!disabled"] if self._path else ["disabled"])

    def _take(self) -> None:
        step = self._labels.get(self._choice.get())
        if step is None:
            return
        self._path = (*self._path, step.slot)
        self.refresh()
        self._on_change()

    def _drop(self) -> None:
        self._path = self._path[:-1]
        self.refresh()
        self._on_change()


class SchemaRuleDialog(tk.Toplevel):
    """A rule reaching across members of a Schema.

    Its arguments are routes rather than values, so each one is a path picker.
    Changing the anchor rebuilds them all: a path is meaningless without the
    entity it starts from.
    """

    def __init__(
        self, parent: tk.Misc, title: str, draft, anchors, rules, parameters_for, steps_for, render, problem: str = ""
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result = None
        self._draft = draft
        self._problem = problem
        self._parameters_for = parameters_for
        self._steps_for = steps_for
        self._render = render
        self._anchors = {c.label: c.id for c in anchors}
        self._rules = {c.label: c.id for c in rules}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Anchored on").grid(row=0, column=0, sticky="w", pady=2)
        self._anchor = tk.StringVar(
            value=next((c.label for c in anchors if c.id == _text(draft.anchor)), anchors[0].label if anchors else "")
        )
        anchor_box = ttk.Combobox(body, textvariable=self._anchor, values=[c.label for c in anchors], state="readonly")
        anchor_box.grid(row=0, column=1, sticky="ew", pady=2)
        anchor_box.bind("<<ComboboxSelected>>", lambda _e: self._anchor_changed())

        ttk.Label(body, text="Rule").grid(row=1, column=0, sticky="w", pady=2)
        self._rule = tk.StringVar(value=next((c.label for c in rules if c.id == _text(draft.validator)), ""))
        rule_box = ttk.Combobox(body, textvariable=self._rule, values=[c.label for c in rules], state="readonly")
        rule_box.grid(row=1, column=1, sticky="ew", pady=2)
        rule_box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())

        self._paths_frame = ttk.Frame(body)
        self._paths_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._paths_frame.columnconfigure(0, weight=1)
        self._pickers: dict[str, PathPicker] = {}

        ttk.Label(body, text="Message when it fails").grid(row=3, column=0, sticky="w", pady=2)
        self._message = tk.StringVar(value=draft.message)
        ttk.Entry(body, textvariable=self._message).grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(
            body,
            text="Enforced in the application: a rule spanning two tables is not a check constraint.",
            foreground="#4f4f4f",
            wraplength=420,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._error = tk.StringVar(value=self._problem)
        ttk.Label(body, textvariable=self._error, foreground="#a01b0b", wraplength=420).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=self._accept).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._rebuild()

    def _collected(self):
        from dataclasses import replace
        from uuid import UUID

        anchor = self._anchors.get(self._anchor.get())
        rule = self._rules.get(self._rule.get())
        return replace(
            self._draft,
            anchor=UUID(anchor) if anchor else None,
            validator=UUID(rule) if rule else None,
            paths={name: picker.path for name, picker in self._pickers.items()},
            message=self._message.get(),
        )

    def _anchor_changed(self) -> None:
        """A path is meaningless without the entity it starts from."""
        self._draft.paths = {}
        self._pickers = {}
        self._rebuild()

    def _rebuild(self) -> None:
        for child in self._paths_frame.winfo_children():
            child.destroy()
        kept = {name: picker.path for name, picker in self._pickers.items()}
        self._pickers = {}
        current = self._collected()
        for index, name in enumerate(self._parameters_for(current)):
            picker = PathPicker(
                self._paths_frame,
                f"{name}:",
                kept.get(name, self._draft.paths.get(name, ())),
                lambda prefix, a=current.anchor: self._steps_for(a, prefix),
                lambda path, a=current.anchor: self._render(a, path),
                self._rebuild_types,
            )
            picker.grid(row=index, column=0, sticky="ew")
            self._pickers[name] = picker

    def _rebuild_types(self) -> None:
        """The `value` path decides the types the other parameters need, so
        finishing it may change what the rest of the dialog is asking for."""
        wanted = list(self._parameters_for(self._collected()))
        if list(self._pickers) != wanted:
            self._rebuild()

    def _accept(self) -> None:
        self.result = self._collected()
        self.destroy()

    def ask(self):
        self.grab_set()
        self.wait_window(self)
        return self.result


def edit_schema_rule(parent, title, draft, anchors, rules, parameters_for, steps_for, render, problem: str = ""):
    return SchemaRuleDialog(parent, title, draft, anchors, rules, parameters_for, steps_for, render, problem).ask()


class RuleDialog(tk.Toplevel):
    """Attach a rule, and supply what it asks for.

    The arguments are not a fixed set of boxes: which ones appear, and what
    each expects, comes from the chosen validator inferred against the value it
    will be given. So `between` on a Money type asks for two decimals, and the
    same rule on a date asks for two dates. Changing the rule rebuilds them.
    """

    def __init__(self, parent: tk.Misc, title: str, draft, rules, slots, parameters_for, problem: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result = None
        self._draft = draft
        self._parameters_for = parameters_for
        self._rules = {c.label: c.id for c in rules}
        self._slots = {c.label: c.id for c in slots}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        row = 0
        if slots:
            ttk.Label(body, text="Applies to").grid(row=row, column=0, sticky="w", pady=2)
            self._slot = tk.StringVar(value=next((c.label for c in slots if c.id == _text(draft.slot)), slots[0].label))
            box = ttk.Combobox(body, textvariable=self._slot, values=[c.label for c in slots], state="readonly")
            box.grid(row=row, column=1, sticky="ew", pady=2)
            # which slot decides the value's type, which decides which rules
            # fit and what they ask for, so both are rebuilt when it changes
            box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
            row += 1
        else:
            self._slot = None

        ttk.Label(body, text="Rule").grid(row=row, column=0, sticky="w", pady=2)
        self._rule = tk.StringVar(value=next((c.label for c in rules if c.id == _text(draft.validator)), ""))
        chooser = ttk.Combobox(body, textvariable=self._rule, values=[c.label for c in rules], state="readonly")
        chooser.grid(row=row, column=1, sticky="ew", pady=2)
        chooser.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        row += 1

        self._arguments_at = row
        self._argument_widgets: dict[str, tk.StringVar] = {}
        self._argument_frame = ttk.Frame(body)
        self._argument_frame.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._argument_frame.columnconfigure(1, weight=1)
        row += 1

        ttk.Label(body, text="Message when it fails").grid(row=row, column=0, sticky="w", pady=2)
        self._message = tk.StringVar(value=draft.message)
        ttk.Entry(body, textvariable=self._message).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        self._error = tk.StringVar(value=problem)
        ttk.Label(body, textvariable=self._error, foreground="#a01b0b", wraplength=380).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=self._accept).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._rebuild()

    def _collected(self):
        from dataclasses import replace
        from uuid import UUID

        chosen = self._rules.get(self._rule.get())
        slot = self._slots.get(self._slot.get()) if self._slot is not None else None
        return replace(
            self._draft,
            validator=UUID(chosen) if chosen else None,
            slot=UUID(slot) if slot else None,
            arguments={name: var.get() for name, var in self._argument_widgets.items()},
            message=self._message.get(),
        )

    def _rebuild(self) -> None:
        """Ask for what this rule needs, and nothing else."""
        for child in self._argument_frame.winfo_children():
            child.destroy()
        kept = {name: var.get() for name, var in self._argument_widgets.items()}
        self._argument_widgets = {}
        wanted = self._parameters_for(self._collected())
        for index, (name, kind) in enumerate(wanted.items()):
            ttk.Label(self._argument_frame, text=f"{name} ({kind})").grid(row=index, column=0, sticky="w", pady=2)
            variable = tk.StringVar(value=kept.get(name, self._draft.arguments.get(name, "")))
            ttk.Entry(self._argument_frame, textvariable=variable).grid(
                row=index, column=1, sticky="ew", pady=2, padx=(8, 0)
            )
            self._argument_widgets[name] = variable

    def _accept(self) -> None:
        self.result = self._collected()
        self.destroy()

    def ask(self):
        self.grab_set()
        self.wait_window(self)
        return self.result


def _text(value) -> str | None:
    return str(value) if value is not None else None


def edit_rule(parent: tk.Misc, title: str, draft, rules, slots, parameters_for, problem: str = ""):
    return RuleDialog(parent, title, draft, rules, slots, parameters_for, problem).ask()


class SlotDialog(tk.Toplevel):
    """Build or edit one slot.

    A dialog rather than an editable cell: inline editing in a Treeview is
    fiddly, and a sub-form that appears and disappears makes the pane jump. The
    cost is a modal for every change, which is bearable because slots are
    usually added rather than tweaked.

    Everything it offers — which properties, which targets, which types may
    narrow an inherited one — is computed elsewhere and handed in.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        draft,
        property_choices=(),
        target_choices=(),
        type_choices=(),
        editing_name: bool = True,
        problem: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result = None
        self._draft = draft
        self._error = tk.StringVar(value=problem)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        row = 0

        # not `_name`: that is the widget's own name in tkinter, and assigning
        # over it makes destroy() fail with "unhashable type: 'StringVar'" —
        # every slot dialog raised on the way out
        self._slot_name = tk.StringVar(value=draft.slot_name)
        ttk.Label(body, text="Name").grid(row=row, column=0, sticky="w", pady=2)
        name_entry = ttk.Entry(body, textvariable=self._slot_name, width=32)
        name_entry.grid(row=row, column=1, sticky="ew", pady=2)
        if not editing_name:
            name_entry.state(["readonly"])
        row += 1

        self._pickers: dict[str, tuple[tk.StringVar, dict[str, str | None]]] = {}

        def picker(label: str, key: str, choices, current) -> None:
            nonlocal row
            by_label = {c.label: c.id for c in choices}
            shown = next((c.label for c in choices if c.id == current), "\u2014 none \u2014")
            variable = tk.StringVar(value=shown)
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Combobox(body, textvariable=variable, values=[c.label for c in choices], state="readonly").grid(
                row=row, column=1, sticky="ew", pady=2
            )
            self._pickers[key] = (variable, by_label)
            row += 1

        if draft.kind == "value":
            picker("Property", "property", property_choices, str(draft.property) if draft.property else None)
            if type_choices:
                picker(
                    "Narrow to",
                    "type_override",
                    type_choices,
                    str(draft.type_override) if draft.type_override else None,
                )
        else:
            picker("Points at", "target", target_choices, str(draft.target) if draft.target else None)

        self._required = tk.BooleanVar(value=draft.required)
        ttk.Label(body, text="Required").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Checkbutton(body, variable=self._required).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        if draft.kind == "value":
            self._default = tk.StringVar(value=draft.default_text)
            ttk.Label(body, text="Default").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=self._default).grid(row=row, column=1, sticky="ew", pady=2)
            row += 1
        else:
            self._inverse = tk.StringVar(value=draft.inverse_name)
            ttk.Label(body, text="Reverse name").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=self._inverse).grid(row=row, column=1, sticky="ew", pady=2)
            row += 1
            self._on_delete = tk.StringVar(value=draft.on_delete)
            ttk.Label(body, text="When the target goes").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Combobox(
                body,
                textvariable=self._on_delete,
                values=["restrict", "cascade", "set_null"],
                state="readonly",
            ).grid(row=row, column=1, sticky="ew", pady=2)
            row += 1

        ttk.Label(body, textvariable=self._error, foreground="#a01b0b", wraplength=340).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=self._accept).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        name_entry.focus_set()

    def _collect(self):
        from dataclasses import replace
        from uuid import UUID

        values = {"slot_name": self._slot_name.get(), "required": self._required.get()}
        for key, (variable, by_label) in self._pickers.items():
            chosen = by_label.get(variable.get())
            values[key] = UUID(chosen) if chosen else None
        if self._draft.kind == "value":
            values["default_text"] = self._default.get()
        else:
            values["inverse_name"] = self._inverse.get()
            values["on_delete"] = self._on_delete.get()
        return replace(self._draft, **values)

    def _accept(self) -> None:
        self.result = self._collect()
        self.destroy()

    def ask(self):
        self.grab_set()
        self.wait_window(self)
        return self.result


def edit_slot(parent: tk.Misc, title: str, draft, problem: str = "", **choices):
    """`problem` reopens the dialog carrying the reason the last attempt was
    refused, so a rejected slot is corrected rather than retyped."""
    return SlotDialog(parent, title, draft, problem=problem, **choices).ask()


class DeleteConfirmation(tk.Toplevel):
    """What a delete would do, before it does it.

    No delete is refused, so this is not a gate — it is the only chance to see
    the damage. It is one undo step either way, which the dialog says, because
    a reversible action is a different decision from an irreversible one.
    """

    def __init__(self, parent: tk.Misc, impact) -> None:
        super().__init__(parent)
        self.title(impact.title)
        self.transient(parent)
        self.result = False

        head = ttk.Frame(self, padding=12)
        head.pack(fill="x")
        ttk.Label(head, text=impact.title, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        if impact.removing:
            ttk.Label(head, text="Removing " + ", ".join(impact.removing)).pack(anchor="w")
        ttk.Label(head, text=impact.summary(), wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))

        if impact.destructive:
            warning = ttk.Frame(self, padding=(12, 0))
            warning.pack(fill="x")
            ttk.Label(
                warning,
                text=(
                    "This changes the shape of other entities, not just their "
                    "references: they lose every slot they inherit."
                ),
                foreground="#a01b0b",
                wraplength=520,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))

        if impact.groups:
            body = ttk.Frame(self, padding=12)
            body.pack(fill="both", expand=True)
            detail = tk.Text(
                body,
                height=min(14, 2 + impact.affected + len(impact.groups)),
                width=72,
                wrap="none",
                background="#ffffff",
                relief="solid",
                borderwidth=1,
            )
            for group in impact.groups:
                detail.insert("end", f"{group.heading}\n")
                for line in group.lines:
                    detail.insert("end", f"    {line}\n")
                detail.insert("end", "\n")
            detail.configure(state="disabled")
            detail.pack(fill="both", expand=True)

        if impact.subtree:
            preview = ttk.Frame(self, padding=(12, 0, 12, 12))
            preview.pack(fill="both", expand=True)
            ttk.Label(
                preview,
                text="The whole subtree goes. This is the part of the file that would be removed:",
                wraplength=520,
                justify="left",
            ).pack(anchor="w", pady=(0, 4))
            box = tk.Text(
                preview, height=10, width=72, wrap="none", background="#ffffff", relief="solid", borderwidth=1
            )
            box.insert("1.0", impact.subtree)
            box.configure(state="disabled")
            bar = ttk.Scrollbar(preview, orient="vertical", command=box.yview)
            box.configure(yscrollcommand=bar.set)
            bar.pack(side="right", fill="y")
            box.pack(side="left", fill="both", expand=True)

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Label(buttons, text="One undo step.", foreground="#4f4f4f").pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Delete", command=self._accept).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _e: self.destroy())

    def _accept(self) -> None:
        self.result = True
        self.destroy()

    def ask(self) -> bool:
        self.grab_set()
        self.wait_window(self)
        return self.result


def confirm_delete(parent: tk.Misc, impact) -> bool:
    return DeleteConfirmation(parent, impact).ask()


def choose(parent: tk.Misc, title: str, prompt: str, options: list[tuple[str, str]]) -> str | None:
    if not options:
        return None
    return Chooser(parent, title, prompt, options).ask()
