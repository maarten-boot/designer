"""Export one Schema of a model file from a source checkout (spec §9.6).

    python3 tools/export_schema.py examples/sales.json sales_schema
    python3 tools/export_schema.py examples/sales.json sales_schema -o sales.export.json

A thin wrapper over `designer_model.cli.export_main`, which an installed copy
runs as `designer-export`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/designer-model/src")
)

from designer_model.cli import export_main

if __name__ == "__main__":
    raise SystemExit(export_main())
