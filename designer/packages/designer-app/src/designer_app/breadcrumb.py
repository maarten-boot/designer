"""The context breadcrumb.

Text, and nothing else. It is not decoration — the active Context filters every
column and decides where a new item is created, so with the Context column
collapsed this is the only indicator of both — but saying where you are and
being a way to move are different jobs, and the Context column already does the
second one. Links and a dropdown here made a label look like a control.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from uuid import UUID

from designer_model import Model

from .rows import context_label

SEPARATOR = "\u203a"  # a right-pointing angle quote


class Breadcrumb(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._label = ttk.Label(self, text="")
        self._label.pack(side="left")

    def show(self, model: Model, context: UUID | None) -> None:
        path = context_label(model, context, f" {SEPARATOR} ")
        self._label.configure(
            text="(no context)" if path == "(none)" else f"Context:  {path}",
            foreground="#888888" if path == "(none)" else "",
        )

    @property
    def text(self) -> str:
        return str(self._label.cget("text"))
