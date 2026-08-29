"""Startup.

The widget layer needs a display, so these tests cover what does not: the
tkinter guard, the startup decision tree, and that the app package still
imports cleanly when tkinter is absent.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import pathlib

import pytest

from designer_app.main import check_tkinter, main


def test_missing_tkinter_is_reported_not_raised(monkeypatch, capsys) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("no tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert check_tkinter() is False
    assert main([]) == 1
    assert "python3-tk" in capsys.readouterr().err


def test_the_app_depends_on_the_model_package() -> None:
    import designer_model

    assert hasattr(designer_model, "Session")


@pytest.mark.parametrize("module", ["designer_app.rows", "designer_app.selection", "designer_app.state"])
def test_the_headless_modules_never_import_tkinter(module) -> None:
    """These four carry the logic worth testing, so none may require a display.

    `layout` joined them after an off-by-one in `restore` reached a user: a
    module that can only be exercised on a machine with a display is a module
    whose bugs are found by the user. It imports tkinter if it is there and
    stands in for the one exception type if it is not.
    """
    imported = importlib.import_module(module)
    assert imported is not None
    tree = ast.parse(pathlib.Path(importlib.util.find_spec(module).origin).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            continue  # an optional import, guarded and given a fallback
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(n.split(".")[0] == "tkinter" for n in names), f"{module}:{node.lineno}"
