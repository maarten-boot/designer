"""The window.

A vertical paned window holding the six columns above and the editor below.

Almost nothing here decides anything. Which rows a column shows, what a
selection highlights, which fields a form has and which choices they offer all
live in modules that import without a display; this one wires them to widgets.
That is deliberate — the interesting parts stay testable.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import UUID

from designer_model import Deriver, Session, membership
from designer_model.commands import AddItem, Command, Macro, SetField
from designer_model.expressions import tokens
from designer_model.model import Type, Validator
from designer_model.stdlib import standard_library

from . import bindings as bindingedit
from . import findings as findingview
from . import forms
from . import rows as rowbuild
from . import slots as slotedit
from .breadcrumb import Breadcrumb
from .columns import ColumnView
from .dialogs import FindingsWindow, choose, confirm_delete, edit_rule, edit_slot
from .factory import duplicate, new_item
from .formview import FRAME_STYLE, PANEL, FormView
from .impact import summarise
from .layout import CollapseManager
from .scrolling import ScrollingArea
from .selection import Selection, choose_base_type, focus, reveal_target, tags_for, updated
from .state import COLUMNS, TITLES, Settings, config_dir
from .tooltip import attach

MIN_WIDTH, MIN_HEIGHT = 1024, 768


class DesignerApp(tk.Tk):
    def __init__(self, session: Session, settings: Settings) -> None:
        super().__init__()
        self.session = session
        self.settings = settings
        self.library = standard_library()
        self.selection = Selection()
        self._autosave_job: str | None = None

        self.title("Designer")
        self._size_window()
        self._build_menu()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # through `updated`, so the context is marked active and shows as
        # chosen; built directly it would be selected but not current
        self.selection = updated(Selection(), "context", rowbuild.default_context(session.model))
        self.refresh()

    # --- window -------------------------------------------------------------

    def _size_window(self) -> None:
        # clamped: a minimum larger than the screen leaves parts of the window
        # unreachable, which is worse than a cramped layout
        width = min(MIN_WIDTH, self.winfo_screenwidth())
        height = min(MIN_HEIGHT, self.winfo_screenheight())
        self.minsize(width, height)
        if self.settings.window_geometry:
            self.geometry(self.settings.window_geometry)
        else:
            self._maximise()

    def _maximise(self) -> None:
        """No portable call exists for this."""
        try:
            if sys.platform == "win32":
                self.state("zoomed")
            elif sys.platform == "darwin":
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
            else:
                self.attributes("-zoomed", True)
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    # --- menu ---------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self, tearoff=False)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_file)
        self._recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label="Open Recent", menu=self._recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        file_menu.add_command(label="Save As…", command=lambda: self.save(ask=True))
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        self._column_vars: dict[str, tk.BooleanVar] = {}
        for name in COLUMNS:
            var = tk.BooleanVar(value=name not in self.settings.collapsed_columns)
            view_menu.add_checkbutton(
                label=TITLES[name],
                variable=var,
                command=lambda n=name: self._toggle_column(n),
            )
            self._column_vars[name] = var
        view_menu.add_separator()
        self._show_builtins = tk.BooleanVar(value=self.settings.show_builtins)
        view_menu.add_checkbutton(label="Show built-in validators", variable=self._show_builtins, command=self.refresh)
        view_menu.add_separator()
        findings_menu = tk.Menu(view_menu, tearoff=False)
        self._finding_level = tk.StringVar(value=self.settings.finding_level)
        for name, label in findingview.LEVEL_LABELS.items():
            findings_menu.add_radiobutton(
                label=label,
                value=name,
                variable=self._finding_level,
                command=self._set_finding_level,
            )
        view_menu.add_cascade(label="Findings shown", menu=findings_menu)
        view_menu.add_separator()
        view_menu.add_command(label="Reset layout", command=self._reset_layout)
        menubar.add_cascade(label="View", menu=view_menu)

        model_menu = tk.Menu(menubar, tearoff=False)
        model_menu.add_command(
            label="Check model and list findings\u2026",
            accelerator="F5",
            command=self.show_findings,
        )
        menubar.add_cascade(label="Model", menu=model_menu)

        self.configure(menu=menubar)
        self.bind_all("<Control-o>", lambda _e: self.open_file())
        self.bind_all("<Control-s>", lambda _e: self.save())
        self.bind_all("<Control-z>", lambda _e: self.undo())
        self.bind_all("<Control-y>", lambda _e: self.redo())
        self.bind_all("<F5>", lambda _e: self.show_findings())
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        self._recent_menu.delete(0, "end")
        for path, available in self.settings.recent():
            label = Path(path).name if available else f"{Path(path).name}  (unavailable)"
            self._recent_menu.add_command(
                label=label,
                state="normal" if available else "disabled",
                command=lambda p=path: self.open_path(Path(p)),
            )
        if not self.settings.recent_files:
            self._recent_menu.add_command(label="(nothing yet)", state="disabled")

    # --- layout -------------------------------------------------------------

    def _build_layout(self) -> None:
        outer = ttk.PanedWindow(self, orient="vertical")
        outer.pack(fill="both", expand=True)

        self._upper = ttk.PanedWindow(outer, orient="horizontal")
        outer.add(self._upper, weight=3)

        self.columns: dict[str, ColumnView] = {}
        for name in COLUMNS:
            view = ColumnView(
                self._upper,
                TITLES[name],
                on_select=self._on_select,
                on_sort=self._toggle_sort,
                on_new=self._new_item,
                on_duplicate=self._duplicate_item,
                on_delete=self._delete_item,
            )
            view.bind("<<FilterChanged>>", lambda _e: self.refresh())
            view.set_sort(name in self.settings.sort_descending)
            self.columns[name] = view
            self._upper.add(view, weight=1)

        lower = ttk.Frame(outer)
        outer.add(lower, weight=2)

        self.breadcrumb = Breadcrumb(lower)
        self.breadcrumb.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Separator(lower, orient="horizontal").pack(fill="x", padx=6)
        self._editor_area = ScrollingArea(lower, background=PANEL, style=FRAME_STYLE)
        self._editor_area.pack(fill="both", expand=True, padx=6, pady=6)
        self.editor = FormView(
            self._editor_area.interior,
            on_commit=self._commit_field,
            on_action=self._form_action,
        )
        self.editor.pack(fill="both", expand=True)

        self.status = ttk.Label(self, anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(fill="x", side="bottom")
        self.status.configure(cursor="hand2")
        self.status.bind("<Button-1>", lambda _e: self.show_findings())
        attach(self.status, "Click to list every finding, or press F5")
        self._findings_window: FindingsWindow | None = None

        self.collapse = CollapseManager(
            self._upper, list(COLUMNS), dict(self.columns), dict(self.settings.column_widths)
        )
        for name in self.settings.collapsed_columns:
            self.collapse.collapse(name)
        if self.settings.sash_positions:
            # sash positions are ignored unless the window has been mapped
            self.after_idle(self._restore_sashes)

    def _restore_sashes(self) -> None:
        for index, position in enumerate(self.settings.sash_positions):
            try:
                self._upper.sashpos(index, position)
            except tk.TclError:
                break

    def _set_finding_level(self) -> None:
        self.settings.finding_level = self._finding_level.get()
        self._update_status()
        if self._findings_window is not None and self._findings_window.winfo_exists():
            self.show_findings()

    def _toggle_sort(self, title: str) -> None:
        column = next(key for key, value in TITLES.items() if value == title)
        if column in self.settings.sort_descending:
            self.settings.sort_descending.remove(column)
        else:
            self.settings.sort_descending.append(column)
        self.columns[column].set_sort(column in self.settings.sort_descending)
        self.refresh()

    def _descending(self, column: str) -> bool:
        return column in self.settings.sort_descending

    def _toggle_column(self, name: str) -> None:
        self.collapse.toggle(name)
        self._column_vars[name].set(not self.collapse.is_collapsed(name))

    def _reset_layout(self) -> None:
        self.collapse.reset()
        for var in self._column_vars.values():
            var.set(True)
        # the remembered sash positions are part of the old layout too, so a
        # reset that left them in place would only be half a reset
        self.settings.sash_positions = []
        self.settings.column_widths = {}

    # --- content ------------------------------------------------------------

    def refresh(self) -> None:
        model = self.session.model
        context = self.selection.context
        result = focus(model, self.selection)

        def extra(ids) -> dict[str, tuple[str, ...]]:
            return {str(i): tags_for(i, result) for i in ids if tags_for(i, result)}

        def text(column: str) -> str:
            return self.columns[column].filter_text

        data = {
            "context": rowbuild.contexts(model, text("context"), self._descending("context")),
            "schema": rowbuild.schemas(model, context, text("schema"), self._descending("schema")),
            "entity": rowbuild.entities(model, context, text("entity"), self._descending("entity")),
            "property": rowbuild.properties(model, context, text("property"), self._descending("property")),
            "type": rowbuild.types(model, context, text("type"), self._descending("type")),
            "validator": rowbuild.validators(
                model,
                context,
                text("validator"),
                library=self.library,
                show_builtins=self._show_builtins.get(),
                descending=self._descending("validator"),
            ),
        }
        for name, column in data.items():
            row_ids = [r.uuid for r in column.rows if r.uuid]
            view = self.columns[name]
            view.show(
                column,
                extra(row_ids),
                reveal=reveal_target(row_ids, result),
                select=self._selected_row(name),
            )
            # only one column is what the editor is showing; the rest keep a
            # muted selection so an earlier choice still reads as chosen
            view.set_active(name == self.selection.active)

        self.breadcrumb.show(model, context)
        self._describe_selection()
        self._update_status()

    def _selected_row(self, column: str) -> object:
        """What the column should show as chosen.

        The Type column may rest on a base type, which has no identity to hold
        in the selection's uuid fields.
        """
        if column == "type" and self.selection.base_type is not None:
            return f"{rowbuild.BASE_PREFIX}{self.selection.base_type}"
        return getattr(self.selection, column, None)

    def _current_item(self) -> UUID | None:
        """What the editor shows: the column chosen most recently.

        Not the rightmost. The columns run from primitives to deliverable, so
        choosing a Type after a Property would otherwise leave the Property in
        the form and nothing would appear to have happened.
        """
        return self.selection.active_item()

    def _describe_selection(self) -> None:
        if self.selection.base_type is not None and self.selection.active == "type":
            spec = forms.describe_base_type(self.session.model, self.selection.base_type)
            if spec is not None:
                self.editor.show(spec)
                self._editor_area.to_top()
                return
        uuid = self._current_item()
        if uuid is None:
            self.editor.clear("Select an item to edit it.")
            return
        spec = forms.describe(self.session.model, uuid, self.library, self.selection.context, self.session.report)
        if spec is None:
            self.editor.clear("That item is gone.")
            return
        self.editor.show(spec)
        # a new form starts at its beginning, not wherever the last one was left
        self._editor_area.to_top()

    # --- editing ------------------------------------------------------------

    def _commit_field(self, uuid: UUID, key: str, value: object) -> None:
        """One committed edit, one undo step, applied to the item the form was
        built for — not to whatever is selected by the time it arrives."""
        item = self.session.model.index().get(uuid)
        if item is None:
            return
        spec = forms.describe(self.session.model, uuid, self.library, self.selection.context)
        entry = spec.by_key(key) if spec else None
        if entry is None:
            return
        converted = self._convert(entry.converter, value, item)
        if converted == getattr(item, key, None):
            return
        if isinstance(item, Validator) and key == "kind":
            self.session.execute(self._change_validator_kind(item, str(converted)))
            self.refresh()
            return
        self.session.execute(SetField(uuid, key, converted, label=f"edit {entry.label.lower()}"))
        self.refresh()

    def _change_validator_kind(self, item: Validator, kind: str) -> Command:
        """Switch between leaf and composite, translating the expression.

        A composite stores its operands as identities and shows them as names.
        Changing the kind without translating would leave the text meaning
        something different from what it says: names where identities belong,
        or identities on screen where names should be. One step, because the
        two changes are one decision.
        """
        names = forms.validator_names(self.session.model, self.library, item.context)
        if kind == "composite":
            expression = tokens.to_stored(
                item.expression, forms.resolver(self.session.model, self.library, item.context)
            )
        else:
            expression = tokens.to_display(item.expression, names).text
        changes = [SetField(item.uuid, "kind", kind)]
        if expression != item.expression:
            changes.append(SetField(item.uuid, "expression", expression))
        return Macro(f"make {kind}", changes)

    def _convert(self, converter: str, value: object, item) -> object:
        if converter == forms.BOOL:
            return bool(value)
        if converter == forms.ITEM_REF:
            return forms.parse_item_ref(value if isinstance(value, str) else None)
        if converter == forms.TYPE_REF:
            return forms.parse_type_ref(value if isinstance(value, str) else None)
        if converter == forms.COMPOSITE:
            # names on screen, identities in the file; a name that resolves to
            # nothing is left as written, so the commit always succeeds and the
            # checker reports what it could not resolve
            return tokens.to_stored(str(value), forms.resolver(self.session.model, self.library, item.context))
        return value

    # --- table actions ------------------------------------------------------

    def _form_action(self, uuid: UUID, key: str, action: str, row_id: str | None) -> None:
        """A button beside a table in the form."""
        handler = {
            "add_member": self._add_member,
            "remove_member": self._remove_member,
            "close_schema": self._close_schema,
            "fork_builtin": self._fork_builtin,
            "add_value_slot": self._add_value_slot,
            "add_reference_slot": self._add_reference_slot,
            "edit_slot": self._edit_slot,
            "override_slot": self._override_slot,
            "remove_slot": self._remove_slot,
            "move_slot_up": self._move_slot_up,
            "move_slot_down": self._move_slot_down,
            "add_rule": self._add_rule,
            "edit_rule": self._edit_rule,
            "remove_rule": self._remove_rule,
        }.get(action)
        if handler is not None:
            handler(uuid, row_id)

    def _label(self, uuid: UUID) -> str:
        item = self.session.model.index().get(uuid)
        return rowbuild.label_of(item) if item else f"<deleted {str(uuid)[:8]}>"

    def _add_member(self, schema: UUID, _row: str | None = None) -> None:
        candidates = membership.addable(self.session.model, schema)
        if not candidates:
            messagebox.showinfo(
                "Nothing to add",
                "Every concrete entity visible from this schema's context is already a member.\n\n"
                "An entity in a sibling context cannot join; move it to a shared "
                "ancestor first.",
            )
            return
        chosen = choose(
            self,
            "Add a member",
            "Nothing joins a schema by itself. Choose an entity to add:",
            sorted(((str(u), self._label(u)) for u in candidates), key=lambda pair: pair[1]),
        )
        if chosen:
            self.apply_membership(membership.plan_add(self.session.model, schema, UUID(chosen)))

    def _remove_member(self, schema: UUID, row_id: str | None) -> None:
        if row_id is None:
            return
        self.apply_membership(membership.plan_remove(self.session.model, schema, UUID(row_id)), removing=True)

    def _close_schema(self, schema: UUID, _row: str | None = None) -> None:
        self.apply_membership(membership.plan_close(self.session.model, schema))

    def apply_membership(self, plan: membership.MembershipPlan, removing: bool = False) -> None:
        """Show what would happen, then do it as one step.

        Adding one entity can cascade into ten through the closure, so the
        cascade is named before it happens rather than discovered afterwards.
        """
        if plan.blocked:
            reasons = "\n".join(f"  {self._label(u)} — {why}" for u, why in plan.blocked)
            messagebox.showwarning("Some entities cannot join", f"{reasons}")
            if not plan.changes:
                return
        if plan.pulled_in and not messagebox.askyesno(
            "Add referenced entities too?",
            f"{self._label(plan.added[0])} references entities that are not members.\n\n"
            "Adding these as well keeps the schema closed:\n\n"
            + "\n".join(f"  {self._label(u)}" for u in plan.pulled_in)
            + f"\n\nAnswering no adds only {self._label(plan.added[0])}, leaving the "
            "schema unclosed.",
        ):
            # declining the cascade means "add the one I asked for", not
            # "do nothing" — refusing the whole add would make closure
            # compulsory by the back door
            plan = plan.only_named()
        if (
            removing
            and plan.dangling
            and not messagebox.askyesno(
                "Leave the schema unclosed?",
                "Removing this leaves references pointing outside the schema:\n\n"
                + "\n".join(f"  {self._label(m)}.{slot} \u2192 {self._label(t)}" for m, slot, t in plan.dangling)
                + "\n\nRemove it anyway?",
            )
        ):
            return
        if not plan.changes:
            return
        label = "remove member" if removing else "add members"
        self.session.execute(plan.command(label))
        self.refresh()

    def _fork_builtin(self, uuid: UUID, _row: str | None = None) -> None:
        """Copy a built-in into the model so it can be edited.

        Rules already bound to the built-in keep pointing at it: the copy is a
        starting point, not a replacement. It keeps the name, so within this
        context it takes precedence — which the model check reports, because a
        name that resolves to two different things is worth knowing about.
        """
        built_in = self.library.get(uuid)
        if built_in is None:
            return
        where = self.selection.context
        if where is None:
            messagebox.showinfo("Choose a context first", "A copy has to live somewhere.")
            return
        copy = duplicate(built_in)
        copy.name = built_in.name
        copy.context = where
        self.session.execute(AddItem(copy, label=f"copy {built_in.name}"))
        self.selection = updated(self.selection, "validator", copy.uuid)
        # the built-ins stay listed: the copy does not replace the original,
        # every rule already bound to it keeps using it, and hiding the list
        # the moment somebody copies from it is disorienting
        self.refresh()

    # --- slots --------------------------------------------------------------

    def _entity_and_slot(self, entity_uuid: UUID, row: str | None):
        entity = self.session.model.index().get(entity_uuid)
        if entity is None:
            return None, None
        if row is None:
            return entity, None
        wanted = UUID(row)
        found = next(
            (s for s in Deriver(self.session.model).effective_slots(entity_uuid) if s.uuid == wanted),
            None,
        )
        return entity, found

    def _slot_choices(self, entity, inherited=None) -> dict:
        return {
            "property_choices": forms.slot_property_choices(self.session.model, entity),
            "target_choices": forms.slot_target_choices(self.session.model, entity),
            "type_choices": (
                forms.narrowing_type_choices(self.session.model, entity, inherited) if inherited is not None else ()
            ),
        }

    def _apply_slot(self, build) -> None:
        """Run a slot change, showing the reason if it is refused.

        The rules — an override must narrow, a required slot may not be set
        null — are checked before anything happens, so the refusal names the
        mistake rather than appearing later as a finding.
        """
        try:
            command = build()
        except slotedit.SlotError as error:
            messagebox.showwarning("That slot cannot be saved", str(error))
            return
        self.session.execute(command)
        self.refresh()

    def _new_slot(self, entity_uuid: UUID, kind: str) -> None:
        entity, _ = self._entity_and_slot(entity_uuid, None)
        if entity is None:
            return
        draft = slotedit.SlotDraft(kind=kind)
        collected = edit_slot(self, f"Add a {kind} slot", draft, **self._slot_choices(entity))
        if collected is None:
            return
        self._apply_slot(lambda: slotedit.add(self.session.model, entity, collected))

    def _add_value_slot(self, entity_uuid: UUID, _row: str | None = None) -> None:
        self._new_slot(entity_uuid, slotedit.VALUE)

    def _add_reference_slot(self, entity_uuid: UUID, _row: str | None = None) -> None:
        self._new_slot(entity_uuid, slotedit.REFERENCE)

    def _edit_slot(self, entity_uuid: UUID, row: str | None) -> None:
        entity, slot = self._entity_and_slot(entity_uuid, row)
        if entity is None or slot is None:
            return
        inherited = Deriver(self.session.model).inherited_slot(entity_uuid, slot.slot_name)
        collected = edit_slot(
            self,
            f"Edit {slot.slot_name}",
            slotedit.SlotDraft.of(slot),
            **self._slot_choices(entity, inherited),
        )
        if collected is None:
            return
        self._apply_slot(lambda: slotedit.edit(self.session.model, entity, slot, collected))

    def _override_slot(self, entity_uuid: UUID, row: str | None) -> None:
        """Narrow an inherited slot rather than copying it.

        The type picker offers only Types that narrow the inherited one, so a
        widening override cannot be built and then refused.
        """
        entity, inherited = self._entity_and_slot(entity_uuid, row)
        if entity is None or inherited is None:
            return
        draft = slotedit.SlotDraft.of(inherited)
        collected = edit_slot(
            self,
            f"Override {inherited.slot_name}",
            draft,
            **self._slot_choices(entity, inherited),
        )
        if collected is None:
            return
        self._apply_slot(lambda: slotedit.add(self.session.model, entity, collected, inherited=inherited))

    def _remove_slot(self, entity_uuid: UUID, row: str | None) -> None:
        entity, slot = self._entity_and_slot(entity_uuid, row)
        if entity is None or slot is None or slot not in entity.slots:
            return
        self._apply_slot(lambda: slotedit.remove(entity, slot))

    def _move_slot(self, entity_uuid: UUID, row: str | None, delta: int) -> None:
        entity, slot = self._entity_and_slot(entity_uuid, row)
        if entity is None or slot is None or slot not in entity.slots:
            return
        self._apply_slot(lambda: slotedit.move(entity, slot, delta))

    def _move_slot_up(self, entity_uuid: UUID, row: str | None) -> None:
        self._move_slot(entity_uuid, row, -1)

    def _move_slot_down(self, entity_uuid: UUID, row: str | None) -> None:
        self._move_slot(entity_uuid, row, 1)

    # --- rules --------------------------------------------------------------

    def _rule_dialog(self, owner, draft, title: str):
        """Offer only rules that fit, and ask only for what they need.

        A rule that cannot type-check against the value it would be given is
        not offered: the alternative is offering it and then reporting an error
        the user could not have avoided.
        """
        deriver = Deriver(self.session.model)
        slots = (
            tuple(
                forms.Choice(str(s.uuid), s.slot_name)
                for s in sorted(deriver.effective_slots(owner.uuid), key=lambda s: s.slot_name)
                if s.is_value
            )
            if not isinstance(owner, Type)
            else ()
        )
        if slots and draft.slot is None:
            draft.slot = UUID(slots[0].id)

        def applicable(current):
            names = []
            for validator in self.session.model.validators:
                if validator.name and bindingedit.fits(
                    self.session.model, self.library, owner, current, validator.uuid
                ):
                    names.append(forms.Choice(str(validator.uuid), validator.name))
            for name in sorted(self.library.names):
                built_in = self.library.by_name(name)
                if bindingedit.fits(self.session.model, self.library, owner, current, built_in.uuid):
                    names.append(forms.Choice(str(built_in.uuid), name))
            return tuple(names)

        return edit_rule(
            self,
            title,
            draft,
            applicable(draft),
            slots,
            lambda current: bindingedit.parameters_for(self.session.model, self.library, owner, current),
        )

    def _rule_owner(self, uuid: UUID):
        return self.session.model.index().get(uuid)

    def _binding(self, owner, row: str | None):
        if row is None:
            return None
        return next((b for b in owner.validators if str(b.uuid) == row), None)

    def _apply_rule(self, build) -> None:
        try:
            command = build()
        except bindingedit.BindingError as error:
            messagebox.showwarning("That rule cannot be saved", str(error))
            return
        self.session.execute(command)
        self.refresh()

    def _add_rule(self, uuid: UUID, _row: str | None = None) -> None:
        owner = self._rule_owner(uuid)
        if owner is None:
            return
        collected = self._rule_dialog(owner, bindingedit.BindingDraft(), "Add a rule")
        if collected is None:
            return
        self._apply_rule(lambda: bindingedit.add(self.session.model, self.library, owner, collected))

    def _edit_rule(self, uuid: UUID, row: str | None) -> None:
        owner = self._rule_owner(uuid)
        binding = self._binding(owner, row) if owner else None
        if owner is None or binding is None:
            return
        collected = self._rule_dialog(owner, bindingedit.BindingDraft.of(binding), "Edit the rule")
        if collected is None:
            return
        self._apply_rule(lambda: bindingedit.edit(self.session.model, self.library, owner, binding, collected))

    def _remove_rule(self, uuid: UUID, row: str | None) -> None:
        owner = self._rule_owner(uuid)
        binding = self._binding(owner, row) if owner else None
        if owner is None or binding is None:
            return
        self._apply_rule(lambda: bindingedit.remove(owner, binding))

    def _delete_item(self, title: str) -> None:
        """Show what would happen, then do it if asked.

        No delete is refused. Once the model is designed to hold incomplete
        states and describe them, a dangling reference is a diagnostic rather
        than a corruption, and refusing only forces the user to dismantle the
        references by hand for the same end state.
        """
        column = next(key for key, value in TITLES.items() if value == title)
        if column == "type" and self.selection.base_type is not None:
            messagebox.showinfo("Built in", "Base types are fixed and cannot be deleted.")
            return
        chosen = getattr(self.selection, column, None)
        if chosen is None:
            return
        if self.library.get(chosen) is not None:
            messagebox.showinfo(
                "Built in",
                "Validators from the standard library are shared by every model "
                "and cannot be deleted. Copy one into the model to make a "
                "version you can change.",
            )
            return
        plan = self.session.plan_delete(chosen)
        if not confirm_delete(self, summarise(self.session.model, plan)):
            return
        self.session.apply(plan)
        self.selection = updated(self.selection, column, None)
        self.refresh()

    def _new_item(self, title: str) -> None:
        column = next(key for key, value in TITLES.items() if value == title)
        created = new_item(TITLES[column], self.selection.context)
        self.session.execute(AddItem(created, label=f"new {TITLES[column]}"))
        self.selection = updated(self.selection, column, created.uuid)
        self.refresh()

    def _duplicate_item(self, title: str) -> None:
        column = next(key for key, value in TITLES.items() if value == title)
        chosen = getattr(self.selection, column, None)
        original = self.session.model.index().get(chosen) if chosen else None
        if original is None:
            self._not_yet("Duplicate")
            return
        copy = duplicate(original)
        self.session.execute(AddItem(copy, label=f"duplicate {TITLES[column]}"))
        self.selection = updated(self.selection, column, copy.uuid)
        self.refresh()

    def _on_select(self, title: str, row_id: str | None) -> None:
        # flush a field the user typed in but did not leave, so an edit is not
        # lost because the next click landed elsewhere
        self.editor.commit_pending()
        name = next(key for key, value in TITLES.items() if value == title)
        if row_id and row_id.startswith(rowbuild.BASE_PREFIX):
            # a base type is selectable but has no identity in the document;
            # an item you can see and cannot inspect is worse than one you
            # cannot see
            new = choose_base_type(self.selection, row_id[len(rowbuild.BASE_PREFIX) :])
            if new != self.selection:
                self.selection = new
                self.refresh()
            return
        uuid = None
        if row_id:
            uuid = UUID(row_id)
        if name == "context" and uuid is None:
            # clearing the context would show every branch at once, including
            # ones that cannot see each other, and would leave a new item with
            # nowhere to go
            uuid = rowbuild.default_context(self.session.model)
        new = updated(self.selection, name, uuid)
        if new == self.selection:
            # Repopulating a column restores its selection, which fires the
            # select event again. Without this the pair would drive each other
            # round the event queue forever: refresh -> show -> select ->
            # refresh. Comparing rather than suppressing, because the event is
            # queued and any flag would be clear again by the time it arrives.
            return
        self.selection = new
        self.refresh()

    # --- actions ------------------------------------------------------------

    def open_file(self) -> None:
        chosen = filedialog.askopenfilename(filetypes=[("Designer model", "*.json"), ("All", "*")])
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> None:
        if not self._confirm_discard():
            return
        try:
            self.session = Session.open(path, undo_limit=self.settings.undo_limit)
        except Exception as error:
            messagebox.showerror("Could not open", f"{path}\n\n{error}")
            return
        self.settings.remember(path)
        self._refresh_recent()
        self.selection = updated(Selection(), "context", rowbuild.default_context(self.session.model))
        self.refresh()

    def save(self, ask: bool = False) -> None:
        target = self.session.path
        if ask or target is None:
            chosen = filedialog.asksaveasfilename(defaultextension=".json")
            if not chosen:
                return
            target = Path(chosen)
        self.session.save(target)
        self.session.clear_autosave(config_dir())
        self.settings.remember(target)
        self._refresh_recent()
        self._update_status()

    def undo(self) -> None:
        if self.session.undo() is not None:
            self.refresh()

    def redo(self) -> None:
        if self.session.redo() is not None:
            self.refresh()

    def full_check(self) -> None:
        self.session.full_check()
        self._update_status()

    def show_findings(self) -> None:
        """Run every rule and list what it found.

        The status line can say how many; only a list can say which, about
        what, and in words.
        """
        report = self.session.full_check()
        rows = findingview.at_least(
            findingview.summarise(self.session.model, report, self.library),
            self.settings.finding_level,
        )
        headline = findingview.headline(report, self.settings.finding_level)
        if self._findings_window is None or not self._findings_window.winfo_exists():
            self._findings_window = FindingsWindow(self, rows, self._go_to_finding)
        self._findings_window.show(rows, headline)
        self._findings_window.deiconify()
        self._findings_window.lift()
        self._update_status()

    def _go_to_finding(self, row) -> None:
        """Take the selection to what a finding is about.

        Including its context: the item may well be somewhere the columns are
        not currently looking, and a list that points at something unreachable
        is only half a list.
        """
        item = self.session.model.index().get(row.item)
        if item is None:
            return
        column = {value: key for key, value in TITLES.items()}.get(type(item).__name__)
        if column is None:
            return
        where = item.uuid if column == "context" else getattr(item, "context", None)
        self.selection = updated(Selection(context=where), column, item.uuid)
        self.refresh()
        self.lift()

    def _not_yet(self, what: str) -> None:
        messagebox.showinfo("Not yet", f"{what} arrives with the forms, in the next round.")

    # --- status and autosave ------------------------------------------------

    def _update_status(self) -> None:
        report = self.session.report
        where = self.session.path.name if self.session.path else "(unsaved)"
        dirty = " \u2022" if self.session.dirty else ""
        level = self.settings.finding_level
        self.status.configure(text=f"{where}{dirty}    {findingview.headline(report, level)}")
        # a list already open follows the model rather than going stale
        if self._findings_window is not None and self._findings_window.winfo_exists():
            rows = findingview.at_least(findingview.summarise(self.session.model, report, self.library), level)
            self._findings_window.show(rows, findingview.headline(report, level))
        self._schedule_autosave()

    def _schedule_autosave(self) -> None:
        """Debounced: a burst of edits produces one write."""
        if not self.session.autosave_owed:
            return
        if self._autosave_job is not None:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(
            self.settings.autosave_delay_ms, lambda: self.session.write_autosave(config_dir())
        )

    # --- closing ------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        if not self.session.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save before continuing?")
        if answer is None:
            return False
        if answer:
            self.save()
        return True

    def _on_close(self) -> None:
        if not self._confirm_discard():
            return
        if self._autosave_job is not None:
            # otherwise the pending callback fires into a destroyed interpreter
            # and tk complains about an invalid command name
            self.after_cancel(self._autosave_job)
            self._autosave_job = None
        collapsed, widths = self.collapse.state()
        self.settings.collapsed_columns = collapsed
        self.settings.column_widths = widths
        self.settings.show_builtins = self._show_builtins.get()
        self.settings.window_geometry = self.winfo_geometry()
        try:
            self.settings.sash_positions = [self._upper.sashpos(i) for i in range(len(self.columns) - 1)]
        except tk.TclError:
            pass
        self.settings.save()
        self.session.clear_autosave(config_dir())
        self.destroy()
