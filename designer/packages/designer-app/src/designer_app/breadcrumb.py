"""The context breadcrumb.

It is not decoration. The active Context filters every column and decides where
a new item is created, so with the Context column collapsed the breadcrumb is
the only indicator of both — which is what makes collapsing that column safe.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from uuid import UUID

from designer_model import Model

from .rows import context_path

SEPARATOR = "\u203a"  # a right-pointing angle quote


def siblings_and_children(model: Model, context: UUID | None) -> list[tuple[UUID, str]]:
    """What the last segment's dropdown offers, so the tree can be navigated
    without restoring the Context column."""
    by_uuid = {c.uuid: c for c in model.contexts}
    parent = by_uuid[context].parent if context in by_uuid else None
    related = [c for c in model.contexts if c.parent == parent or c.parent == context]
    return sorted(((c.uuid, c.name or "<unnamed>") for c in related), key=lambda pair: pair[1])


class Breadcrumb(ttk.Frame):
    def __init__(self, parent: tk.Misc, on_navigate: Callable[[UUID], None]) -> None:
        super().__init__(parent)
        self._on_navigate = on_navigate
        self._model: Model | None = None

    def show(self, model: Model, context: UUID | None) -> None:
        self._model = model
        for child in self.winfo_children():
            child.destroy()

        segments = context_path(model, context)
        if not segments:
            ttk.Label(self, text="(no context)", foreground="#888888").pack(side="left")
            return

        for index, (uuid, name) in enumerate(segments):
            if index:
                ttk.Label(self, text=f" {SEPARATOR} ").pack(side="left")
            last = index == len(segments) - 1
            if last:
                self._final_segment(model, uuid, name)
            else:
                link = ttk.Label(self, text=name, foreground="#1a4fa0", cursor="hand2")
                link.pack(side="left")
                link.bind("<Button-1>", lambda _e, u=uuid: self._on_navigate(u))

    def _final_segment(self, model: Model, uuid: UUID, name: str) -> None:
        options = siblings_and_children(model, uuid)
        if not options:
            ttk.Label(self, text=name, font=("TkDefaultFont", 9, "bold")).pack(side="left")
            return
        chooser = ttk.Menubutton(self, text=name, direction="below")
        menu = tk.Menu(chooser, tearoff=False)
        for other_uuid, other_name in options:
            menu.add_command(label=other_name, command=lambda u=other_uuid: self._on_navigate(u))
        chooser.configure(menu=menu)
        chooser.pack(side="left")
