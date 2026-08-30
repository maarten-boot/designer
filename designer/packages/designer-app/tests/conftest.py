"""Fixtures for tests that need a real window.

The widget suite is silent on a machine without a display and meaningful on one
with it. That split exists because the code was written on a machine with
neither tkinter nor a display: everything testable without one already is, and
this covers the rest for whoever runs it.

The skip itself lives in the test module, not here — a skip mark has to be
evaluated at import time, and a test file cannot import its own conftest.
"""

from __future__ import annotations

import pathlib

import pytest

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture(autouse=True)
def time_limit():
    """Fail rather than hang.

    An event feedback loop in a widget does not raise; it spins. Without a
    limit the whole run stops, the window stays on screen, and there is nothing
    to read. Fifteen seconds is far longer than any test here needs, and the
    traceback names the line that was spinning.
    """
    import signal

    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - Windows
        yield
        return

    def ring(_signum, _frame):
        raise TimeoutError(
            "test exceeded its time limit — most likely an event feedback loop "
            "between refresh and the column repopulating itself"
        )

    previous = signal.signal(signal.SIGALRM, ring)
    signal.alarm(15)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Somewhere to write settings and autosave that is not the real one.

    Without this a test run would overwrite the window geometry, recent files
    and collapse state of whoever ran it.
    """
    directory = tmp_path / "config"
    directory.mkdir()
    # each module that imported the name needs its own copy replaced;
    # raising=False covers the ones that have not imported it
    for target in (
        "designer_app.state.config_dir",
        "designer_app.app.config_dir",
        "designer_app.main.config_dir",
    ):
        monkeypatch.setattr(target, lambda: directory, raising=False)
    return directory


@pytest.fixture
def quiet(monkeypatch):
    """Stub the modal dialogs.

    A test that pops a real dialog blocks forever with nobody to click it, so
    every prompt answers itself and every file chooser declines.
    """
    import designer_app.app as app_module

    # `answer` is what askyesno returns, and a test may set it before acting.
    # Fixed at False it silently exercised only the declining half of every
    # prompt, which is how a test meant to cover the confirming half ended up
    # asserting the wrong thing.
    calls: dict[str, object] = {
        "info": [],
        "error": [],
        "warning": [],
        "ask": [],
        "delete": [],
        "slot_dialogs": [],
        "slot": None,
        "rule_dialogs": [],
        "rule": None,
        "schema_rule_dialogs": [],
        "schema_rule": None,
        "answer": False,
    }

    class Boxes:
        @staticmethod
        def showinfo(title, message=None, **_kw):
            calls["info"].append((title, message))

        @staticmethod
        def showerror(title, message=None, **_kw):
            calls["error"].append((title, message))

        @staticmethod
        def showwarning(title, message=None, **_kw):
            calls["warning"].append((title, message))

        @staticmethod
        def askyesno(title, message=None, **_kw):
            calls["ask"].append((title, message))
            return calls["answer"]

        @staticmethod
        def askyesnocancel(title, message=None, **_kw):
            calls["ask"].append((title, message))
            return False  # do not save, but do continue

    class Files:
        @staticmethod
        def askopenfilename(**_kw):
            return ""

        @staticmethod
        def asksaveasfilename(**_kw):
            return ""

    def confirm_delete(_parent, impact):
        calls["delete"].append(impact)
        return calls["answer"]

    def edit_schema_rule(_parent, title, draft, anchors, rules, parameters_for, steps_for, render):
        calls["schema_rule_dialogs"].append((title, draft, anchors, rules, steps_for))
        return calls["schema_rule"]

    def edit_rule(_parent, title, draft, rules, slots, parameters_for):
        """Return whatever the test put in `rule`, or nothing (Cancel)."""
        calls["rule_dialogs"].append((title, draft, rules, slots, parameters_for))
        return calls["rule"]

    def edit_slot(_parent, title, draft, **choices):
        """Return whatever the test put in `slot`, or nothing (Cancel)."""
        calls["slot_dialogs"].append((title, draft, choices))
        return calls["slot"]

    monkeypatch.setattr(app_module, "messagebox", Boxes)
    monkeypatch.setattr(app_module, "filedialog", Files)
    monkeypatch.setattr(app_module, "confirm_delete", confirm_delete)
    monkeypatch.setattr(app_module, "edit_slot", edit_slot)
    monkeypatch.setattr(app_module, "edit_rule", edit_rule)
    monkeypatch.setattr(app_module, "edit_schema_rule", edit_schema_rule)
    return calls


@pytest.fixture
def app(config, quiet):
    """A live window over the worked example, torn down afterwards."""
    import tkinter

    from designer_model import Session

    from designer_app.app import DesignerApp
    from designer_app.state import Settings

    window = DesignerApp(Session.open(EXAMPLE), Settings())
    window.update()  # a full update, so any startup events are delivered
    yield window
    pending = getattr(window, "_autosave_job", None)
    if pending is not None:
        try:
            window.after_cancel(pending)
        except tkinter.TclError:
            pass
    try:
        window.destroy()
    except tkinter.TclError:
        # a test may have closed it already; teardown must not mask the real
        # failure with one of its own
        pass
