"""designer-model must stay usable without a display (spec §14.1).

A generator, a CLI or a web front end depends on this package; if a GUI import
crept in, they would all inherit it — and on a headless machine they would fail
at import time rather than at use.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "designer_model"


def test_no_tkinter_in_source() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n.split(".")[0] == "tkinter" for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"tkinter imported in {offenders}"


def test_no_tkinter_after_import() -> None:
    """Belt and braces: nothing pulls it in transitively either."""
    code = "import designer_model, sys; print('tkinter' in sys.modules)"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC.parent), "PATH": "/usr/bin:/bin"},
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_only_standard_library() -> None:
    """No third-party dependency may creep in unnoticed."""
    third_party = {"pydantic", "attrs", "yaml", "platformdirs", "dateutil", "sqlalchemy"}
    found = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    assert not (found & third_party), f"third-party import: {found & third_party}"
