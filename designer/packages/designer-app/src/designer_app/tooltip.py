"""Hover tooltips.

tkinter has none, and the controls that most need one are the smallest: a
column toolbar reading `+ = -` tells you nothing until you have pressed all
three and undone the third.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

DELAY_MS = 450
BACKGROUND = "#ffffe0"
BORDER = "#8a8a6a"


class Tooltip:
    """A label that appears under a widget after a pause, and goes on the way out."""

    def __init__(self, widget: tk.Misc, text: str, delay: int = DELAY_MS) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._pending: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        # a press means the user has decided; the hint has served its purpose
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        self._pending = self.widget.after(self.delay, self._show)

    def _cancel(self, _event: object = None) -> None:
        if self._pending is not None:
            self.widget.after_cancel(self._pending)
            self._pending = None
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _show(self) -> None:
        self._pending = None
        try:
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        except tk.TclError:
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            window,
            text=self.text,
            background=BACKGROUND,
            relief="solid",
            borderwidth=1,
            padding=(6, 3),
            wraplength=320,
            justify="left",
        ).pack()
        self._window = window


def attach(widget: tk.Misc, text: str) -> Tooltip:
    return Tooltip(widget, text)
