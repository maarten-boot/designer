"""A Schema's export as a tree of small files (appendix *tree*).

    designer-export model.json sales_schema --tree out/sales_schema

The same document `export.py` writes, cut where a program generating an
application would want to reach in: one file for the Schema, one per table and
one per column. Each file holds the export's own object unchanged, except that
a list of tables or columns becomes a list of `{name, uuid, path}` pointing at
their files, so `assemble()` puts the export back together exactly, which the
tests check.

**Paths are given, never computed.** A name is a valid file name on every
system it has to work on except in two cases: Windows reserves `CON`, `NUL`,
`COM1` and the rest whatever the extension, and two names differing only in
case are one file on Windows and macOS. Either gets `~` and the item's UUID
added, so a reader must follow `path` rather than build it from `name`.
Paths are relative to the tree's root and use `/`, which every system reads.

**A snapshot, replaced whole.** The tree is written beside the target and
swapped in with two renames, so a program reading the old tree sees the old
one or the new one, not a mixture, and a column deleted from the model leaves
no stale file behind. A target that exists and is not a tree written here is
never touched.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
from typing import Any

FORMAT = "designer-schema-tree"
FORMAT_VERSION = 1
ROOT_FILE = "schema.json"

# reserved by Windows as device names, with or without an extension
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10))}


class TreeError(Exception):
    """The tree cannot be written where it was asked for."""


def file_names(items: list[dict[str, Any]]) -> list[str]:
    """A file name for each item, safe on Linux, Windows and macOS alike and
    distinct when case is ignored. Deterministic: the same items give the
    same names."""
    folded: dict[str, int] = {}
    for item in items:
        folded[item["name"].casefold()] = folded.get(item["name"].casefold(), 0) + 1
    names = []
    for item in items:
        name = item["name"]
        if not name or name.upper() in RESERVED or folded[name.casefold()] > 1:
            name = f"{name}~{item['uuid']}"
        names.append(name)
    return names


def files(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every file of the tree, by its path from the root, in the order
    written."""
    out: dict[str, dict[str, Any]] = {}
    root = {"format": FORMAT, "format_version": FORMAT_VERSION}
    tables = document["tables"]
    entries = []
    for table, folder in zip(tables, file_names(tables), strict=True):
        base = f"tables/{folder}"
        columns = []
        column_files: dict[str, dict[str, Any]] = {}
        for column, name in zip(table["columns"], file_names(table["columns"]), strict=True):
            path = f"{base}/columns/{name}.json"
            columns.append({"name": column["name"], "uuid": column["uuid"], "path": path})
            column_files[path] = column
        path = f"{base}/table.json"
        out[path] = {key: (columns if key == "columns" else value) for key, value in table.items()}
        out.update(column_files)
        entries.append({"name": table["name"], "uuid": table["uuid"], "path": path})
    for key, value in document.items():
        if key in ("format", "format_version"):
            root[f"export_{key}"] = value
        else:
            root[key] = entries if key == "tables" else value
    return {ROOT_FILE: root, **out}


def assemble(read: Any) -> dict[str, Any]:
    """The export document back from a tree. `read(path)` gives a file's
    parsed contents. The inverse of `files`, and how a reader can rely on
    the tree holding everything the export does."""
    root = read(ROOT_FILE)
    if root.get("format") != FORMAT:
        raise TreeError(f"{ROOT_FILE} is not a {FORMAT}")
    document: dict[str, Any] = {}
    for key, value in root.items():
        if key in ("format", "format_version"):
            continue
        if key.startswith("export_"):
            document[key.removeprefix("export_")] = value
        elif key == "tables":
            document[key] = []
            for entry in value:
                table = read(entry["path"])
                table["columns"] = [read(c["path"]) for c in table["columns"]]
                document[key].append(table)
        else:
            document[key] = value
    order = ["format", "format_version"]
    return {key: document[key] for key in order + [k for k in document if k not in order]}


def dumps(content: dict[str, Any]) -> str:
    return json.dumps(content, indent=2, ensure_ascii=False) + "\n"


def is_tree(folder: pathlib.Path) -> bool:
    try:
        root = json.loads((folder / ROOT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(root, dict) and root.get("format") == FORMAT


def write(document: dict[str, Any], target: pathlib.Path) -> int:
    """Write the tree to `target`, replacing a tree already there. Returns
    the number of files written."""
    target = pathlib.Path(target)
    if target.exists() and not (target.is_dir() and (not any(target.iterdir()) or is_tree(target))):
        raise TreeError(f"{target} exists and is not a Schema tree; not replacing it")
    content = files(document)
    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = pathlib.Path(tempfile.mkdtemp(prefix=f".{target.name}.new-", dir=target.parent))
    try:
        for path, value in content.items():
            where = fresh / path
            where.parent.mkdir(parents=True, exist_ok=True)
            # bytes, so Windows writes \n as \n: the same tree on every system
            where.write_bytes(dumps(value).encode("utf-8"))
    except BaseException:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    old = None
    if target.exists():
        old = target.parent / f".{target.name}.old-{os.getpid()}"
        target.rename(old)
    try:
        fresh.rename(target)
    except BaseException:
        if old is not None:
            old.rename(target)  # put the previous snapshot back
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)
    return len(content)
