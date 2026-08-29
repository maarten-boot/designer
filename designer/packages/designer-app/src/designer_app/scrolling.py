"""A vertically scrolling area.

The editor grows with the item: an Entity with a dozen slots and a handful of
rules is taller than the pane. Without this the bottom of the form is simply
unreachable, and a pane the user has to enlarge before they can finish reading
is a pane that will be enlarged every time.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


class ScrollingArea(ttk.Frame):
    """A frame whose `interior` can be taller than the space it is given."""

    def __init__(self, parent: tk.Misc, background: str = "#ffffff", style: str = "") -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.interior = ttk.Frame(self.canvas, style=style) if style else ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")

        self.interior.bind("<Configure>", self._interior_resized)
        self.canvas.bind("<Configure>", self._canvas_resized)
        # bound while the pointer is over the area, and released on the way out,
        # so the wheel does not scroll this pane from anywhere in the window
        self.canvas.bind("<Enter>", self._grab_wheel)
        self.canvas.bind("<Leave>", self._release_wheel)

    # --- geometry -----------------------------------------------------------

    def _interior_resized(self, _event: object) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_resized(self, event: tk.Event) -> None:
        # the form fills the width, so its fields stretch rather than sitting
        # in a column the width of their longest label
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_scroll(self, first: str, last: str) -> None:
        """Show the scrollbar only when there is something to scroll."""
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.bar.pack_forget()
        else:
            self.bar.pack(side="right", fill="y", before=self.canvas)
        self.bar.set(first, last)

    def to_top(self) -> None:
        """Called when the contents change: a new form should start at its
        beginning, not wherever the previous one was scrolled to."""
        self.canvas.yview_moveto(0)

    # --- the wheel ----------------------------------------------------------

    def _grab_wheel(self, _event: object) -> None:
        if sys.platform == "linux":
            # X11 reports the wheel as buttons four and five
            self.canvas.bind_all("<Button-4>", self._wheel)
            self.canvas.bind_all("<Button-5>", self._wheel)
        else:
            self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _release_wheel(self, _event: object) -> None:
        for sequence in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.canvas.unbind_all(sequence)

    def _wheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step, "units")
