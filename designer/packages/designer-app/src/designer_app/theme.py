"""Putting a `palette.Palette` on the screen.

`palette` decides the colours and is tested without a display; this module is
the part that tells Tk. It is applied once at start and again whenever the
contrast level changes, and it reaches what is already open: ttk styles are
global, classic widgets are walked and reconfigured, and Treeview tags are set
by `tag_rows`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import palette as pal

_CUE_FONTS: dict[tuple[str, str], tkfont.Font] = {}

# the ttk styles whose text has a disabled state worth mapping
_TEXT_STYLES = (
    "TLabel",
    "TButton",
    "TCheckbutton",
    "TRadiobutton",
    "TEntry",
    "TCombobox",
    "TMenubutton",
    "TLabelframe.Label",
    "TNotebook.Tab",
)


def cue_font(widget: tk.Misc, cue: str) -> tkfont.Font:
    """The default font, italic or bold. One of each per interpreter: a font
    object made per row would be collected while Tk still draws with it."""
    key = (str(widget.tk), cue)
    if key not in _CUE_FONTS:
        made = tkfont.nametofont("TkDefaultFont", root=widget).copy()
        if cue == "italic":
            made.configure(slant="italic")
        else:
            made.configure(weight="bold")
        _CUE_FONTS[key] = made
    return _CUE_FONTS[key]


def tag_rows(tree: ttk.Treeview, palette: pal.Palette | None = None) -> None:
    """The row states and relationships on one Treeview, with a font cue where
    colour alone no longer tells a row apart."""
    palette = palette or pal.current()
    for tag, options in palette.tag_styles().items():
        cue = palette.cues.get(tag)
        if cue:
            tree.tag_configure(tag, font=cue_font(tree, cue), **options)
        else:
            # "" puts the font back to the style's after a cue was set
            tree.tag_configure(tag, font="", **options)


def apply(root: tk.Misc, palette: pal.Palette | None = None) -> None:
    """Black on white, and every pair at the palette's minimum."""
    palette = palette or pal.current()
    text, background = palette.text, palette.background
    chosen = palette.selections["text"]

    style = ttk.Style(root)
    style.configure(
        ".",
        background=background,
        foreground=text,
        fieldbackground=background,
        selectbackground=chosen.background,
        selectforeground=chosen.foreground,
        insertcolor=text,
    )
    style.configure("Treeview", background=background, fieldbackground=background, foreground=text)
    style.configure("Treeview.Heading", background=background, foreground=text)
    for name in _TEXT_STYLES:
        style.map(name, foreground=[("disabled", palette.disabled)])
    style.map("TEntry", fieldbackground=[("readonly", background)])
    style.map("TCombobox", fieldbackground=[("readonly", background)], foreground=[("disabled", palette.disabled)])
    _selection(style, "Treeview", palette.selections["active"])

    # classic widgets read the option database when they are made…
    for option, value in (
        ("*Background", background),
        ("*Foreground", text),
        ("*selectBackground", chosen.background),
        ("*selectForeground", chosen.foreground),
        ("*insertBackground", text),
        ("*disabledForeground", palette.disabled),
        ("*activeBackground", chosen.background),
        ("*activeForeground", chosen.foreground),
        ("*TCombobox*Listbox.background", background),
        ("*TCombobox*Listbox.foreground", text),
    ):
        root.option_add(option, value)
    # …and the ones already made are told
    _walk(root, palette)


def _selection(style: ttk.Style, name: str, selection: pal.Selection) -> None:
    style.map(
        name,
        background=[("selected", selection.background)],
        foreground=[("selected", selection.foreground), ("disabled", pal.current().disabled)],
    )


def install_selections(root: tk.Misc, active_style: str, idle_style: str) -> None:
    """The browser columns' two selection styles: the column the editor is
    showing, and the others."""
    style = ttk.Style(root)
    palette = pal.current()
    _selection(style, active_style, palette.selections["active"])
    _selection(style, idle_style, palette.selections["idle"])


def _walk(widget: tk.Misc, palette: pal.Palette) -> None:
    chosen = palette.selections["text"]
    if isinstance(widget, tk.Menu):
        widget.configure(
            background=palette.background,
            foreground=palette.text,
            activebackground=chosen.background,
            activeforeground=chosen.foreground,
            disabledforeground=palette.disabled,
            selectcolor=palette.text,
        )
    elif isinstance(widget, tk.Text):
        # the foreground is the caller's: a finding is red, a note grey, and
        # the form redraws those itself
        widget.configure(
            background=palette.background,
            insertbackground=palette.text,
            selectbackground=chosen.background,
            selectforeground=chosen.foreground,
        )
    elif isinstance(widget, (tk.Tk, tk.Toplevel, tk.Canvas, tk.Frame)):
        widget.configure(background=palette.background)
    for child in widget.winfo_children():
        _walk(child, palette)
