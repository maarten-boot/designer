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


def choose(parent: tk.Misc, title: str, prompt: str, options: list[tuple[str, str]]) -> str | None:
    if not options:
        return None
    return Chooser(parent, title, prompt, options).ask()
