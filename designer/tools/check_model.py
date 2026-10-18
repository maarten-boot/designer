"""Check a model file from a source checkout.

    python3 tools/check_model.py examples/sales.json

A thin wrapper over `designer_model.cli.check_main`, which an installed copy
runs as `designer-check`. Loads the document, verifies it survives a save/load
round trip unchanged, runs the model check, and reports what it finds. Exits
non-zero on an error, so it can gate a build.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/designer-model/src")
)

from designer_model.cli import check_main

if __name__ == "__main__":
    raise SystemExit(check_main())
