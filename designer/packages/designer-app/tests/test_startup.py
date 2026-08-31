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


def test_a_scrollbar_is_always_packed_before_what_it_scrolls() -> None:
    """The packer allocates in order, so a scrollbar packed after its widget is
    the one squeezed to nothing when space runs short.

    Checked here because it only shows on a narrow window, and the widget tests
    skip on a machine with no display. Scoped to one function at a time: the
    first version of this compared against every pack in the file and blamed a
    correct dialog for a tree in a different class.
    """
    import ast
    import pathlib

    def dotted(node: ast.AST) -> str | None:
        """`self.tree` as "self.tree", not "self".

        Reducing to the root name made every `self.<something>` the same
        widget, and the check blamed two correct dialogs.
        """
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(node.id)
        return ".".join(reversed(parts))

    def packed(node: ast.AST) -> str | None:
        """The widget in a `<widget>.pack(...)` call, if it is one."""
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            return None
        if node.func.attr != "pack":
            return None
        return dotted(node.func.value)

    def scrolls(node: ast.AST) -> str | None:
        """What a Scrollbar's `command=<name>.yview` names."""
        if not isinstance(node, ast.Call):
            return None
        for keyword in node.keywords:
            if keyword.arg == "command" and isinstance(keyword.value, ast.Attribute):
                if keyword.value.attr in {"yview", "xview"}:
                    return dotted(keyword.value.value)
        return None

    wrong = []
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_app"
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            scrolled: dict[str, str] = {}
            order: list[tuple[int, str]] = []
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and (target := scrolls(node.value)):
                    for assigned in node.targets:
                        if isinstance(assigned, ast.Name):
                            scrolled[assigned.id] = target
                if name := packed(node):
                    order.append((node.lineno, name))
            order.sort()
            seen: set[str] = set()
            for line, name in order:
                if name in scrolled and scrolled[name] in seen:
                    wrong.append(f"{path.name}:{line} ({name} after {scrolled[name]})")
                seen.add(name)
    assert wrong == [], f"scrollbar packed after its widget at {wrong}"


def test_widget_tests_only_reach_for_attributes_that_exist() -> None:
    """A renamed handler leaves the tests calling the old name.

    `make sync` cannot catch this: it turns `attr-defined` off, because
    `model.index()` returns `Item` and mypy then objects to every legitimate
    `.slots` and `.identity` in the tests. This looks at one specific thing
    instead — what the tests reach for on the application and its editor —
    which is where a rename actually shows.

    It has been run by hand after every rename this session; a check that
    depends on remembering is not a check.
    """
    import ast
    import pathlib
    import re

    source = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_app"

    def members(path: pathlib.Path, classname: str) -> set[str]:
        found: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and node.name == classname:
                found |= {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
                for inner in ast.walk(node):
                    # assignments only. Counting every `self.x` read meant a
                    # stale reference in the source kept the old name looking
                    # defined, and the check passed a rename it should catch.
                    targets = (
                        inner.targets
                        if isinstance(inner, ast.Assign)
                        else [inner.target]
                        if isinstance(inner, ast.AnnAssign)
                        else []
                    )
                    for target in targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            found.add(target.attr)
        return found

    app = members(source / "app.py", "DesignerApp")
    editor = members(source / "formview.py", "FormView")
    text = pathlib.Path(__file__).with_name("test_widgets.py").read_text()

    inherited = {
        "update",
        "update_idletasks",
        "winfo_exists",
        "winfo_screenwidth",
        "destroy",
        "minsize",
        "title",
        "cget",
        "after_cancel",
        "geometry",
        "event_generate",
        "quit",
    }

    # tk's whole winfo_ vocabulary, and the module dunder the tests use to
    # locate files, are not the application's to define
    def unknown(found: set[str], defined: set[str]) -> list[str]:
        return sorted(
            name for name in found - defined - inherited if not name.startswith("winfo_") and name != "__file__"
        )

    missing = unknown(set(re.findall(r"\bapp\.(_[a-z_]+)", text)), app)
    missing += unknown(set(re.findall(r"app\.editor\.(_?[a-z_]+)", text)), editor)
    assert missing == [], f"the tests call these, and nothing defines them: {missing}"


def test_no_widget_shadows_a_name_tkinter_owns() -> None:
    """`self._name = tk.StringVar(...)` in a dialog overwrote the widget's own
    name, and `destroy()` then failed with "unhashable type: 'StringVar'" every
    time that dialog closed.

    tkinter keeps its bookkeeping in ordinary attributes on the widget, so a
    subclass assigning to one of them breaks the widget rather than being
    caught anywhere.
    """
    import ast
    import pathlib

    reserved = {"_name", "_w", "children", "master", "tk", "widgetName", "_last_child_ids"}
    offenders = []
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_app"
    for path in sorted(root.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr in reserved
                ):
                    offenders.append(f"{path.name}:{node.lineno} self.{target.attr}")
    assert offenders == [], f"these shadow tkinter's own attributes: {offenders}"


def test_widget_tests_never_assert_on_a_stretched_column_width() -> None:
    """`column(..., "width")` reports what tk stretched the column to after
    layout, not what was asked for. Two tests have now been written against it
    — one expecting the columns to differ, one expecting width to equal
    minwidth — and both were wrong in the same way. `minwidth` is what the
    calculation sets.
    """
    import pathlib
    import re

    source = pathlib.Path(__file__).with_name("test_widgets.py").read_text()
    offenders = [
        number for number, line in enumerate(source.splitlines(), start=1) if re.search(r'\.column\([^)]*"width"', line)
    ]
    assert offenders == [], f"assert on minwidth, not width, at lines {offenders}"


def test_widget_tests_never_compare_a_raw_cget_result() -> None:
    """`cget` returns a Tcl object for some options, not a Python string.

    `cget("text") == "x"` happens to work and `cget("cursor") == "hand2"` does
    not, which makes the mistake look correct until it is not. Since the widget
    tests skip on a machine with no display, this catches it there instead.
    """
    import ast
    import pathlib

    source = pathlib.Path(__file__).with_name("test_widgets.py")
    tree = ast.parse(source.read_text())

    def is_cget(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"cget", "itemcget", "entrycget"}
        )

    bare = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                if is_cget(side):
                    bare.append(node.lineno)
    assert bare == [], f"wrap cget in str() at lines {sorted(set(bare))}"
