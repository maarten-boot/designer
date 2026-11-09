"""The export as a tree of files (appendix *tree*)."""

from __future__ import annotations

import json
import pathlib

import pytest

from designer_model import tree
from designer_model.cli import export_main

EXAMPLES = pathlib.Path(__file__).resolve().parents[3] / "examples"
EXAMPLE = EXAMPLES / "sales.json"
SAMPLE = EXAMPLES / "sales_schema.tree"
EXPORTS = sorted(EXAMPLES.glob("*.export.json"))


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reader(root: pathlib.Path):
    return lambda path: _load(root / path)


def _listing(root: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_the_committed_sample_is_what_the_export_writes(tmp_path) -> None:
    """examples/sales_schema.tree is generated, and compared byte for byte."""
    assert export_main([str(EXAMPLE), "sales_schema", "--tree", str(tmp_path / "t")]) == 0
    assert _listing(tmp_path / "t") == _listing(SAMPLE)


@pytest.mark.parametrize("export", EXPORTS, ids=lambda p: p.name)
def test_the_tree_holds_the_whole_export(export, tmp_path) -> None:
    document = _load(export)
    tree.write(document, tmp_path / "t")
    assert tree.assemble(_reader(tmp_path / "t")) == document
    # the same key order too, so a reader re-serialising gets the same bytes
    assert tree.dumps(tree.assemble(_reader(tmp_path / "t"))) == export.read_text(encoding="utf-8")


def test_one_file_per_table_and_per_column() -> None:
    document = _load(EXAMPLES / "sales_schema.export.json")
    paths = list(tree.files(document))
    assert paths[0] == "schema.json"
    assert len(paths) == 1 + sum(1 + len(t["columns"]) for t in document["tables"])
    root = tree.files(document)["schema.json"]
    assert root["format"] == "designer-schema-tree"
    assert root["export_format"] == "designer-schema-export"
    assert root["tables"][0] == {
        "name": "Customer",
        "uuid": document["tables"][0]["uuid"],
        "path": "tables/Customer/table.json",
    }


def test_every_path_named_in_a_file_exists_and_uses_forward_slashes() -> None:
    root = _load(SAMPLE / "schema.json")
    for entry in root["tables"]:
        assert "\\" not in entry["path"]
        table = _load(SAMPLE / entry["path"])
        for column in table["columns"]:
            assert (SAMPLE / column["path"]).is_file()
            assert _load(SAMPLE / column["path"])["uuid"] == column["uuid"]


def test_names_windows_reserves_or_that_differ_only_in_case_get_the_uuid() -> None:
    items = [
        {"name": "con", "uuid": "u1"},
        {"name": "Name", "uuid": "u2"},
        {"name": "name", "uuid": "u3"},
        {"name": "COM1", "uuid": "u4"},
        {"name": "console", "uuid": "u5"},
        {"name": "LPT0", "uuid": "u6"},
    ]
    assert tree.file_names(items) == ["con~u1", "Name~u2", "name~u3", "COM1~u4", "console", "LPT0"]


def test_writing_again_replaces_the_tree_and_leaves_nothing_stale(tmp_path) -> None:
    document = _load(EXAMPLES / "sales_schema.export.json")
    target = tmp_path / "t"
    tree.write(document, target)
    smaller = json.loads(json.dumps(document))
    dropped = smaller["tables"][0]["columns"].pop()
    tree.write(smaller, target)
    assert not (target / "tables" / "Customer" / "columns" / f"{dropped['name']}.json").exists()
    assert tree.assemble(_reader(target)) == smaller
    assert [p.name for p in tmp_path.iterdir()] == ["t"]  # no temporary folders left


def test_a_folder_that_is_not_a_tree_is_never_replaced(tmp_path) -> None:
    target = tmp_path / "mine"
    target.mkdir()
    (target / "notes.txt").write_text("keep me")
    with pytest.raises(tree.TreeError, match="not a Schema tree"):
        tree.write(_load(EXAMPLES / "sales_schema.export.json"), target)
    assert (target / "notes.txt").read_text() == "keep me"
    assert [p.name for p in tmp_path.iterdir()] == ["mine"]


def test_an_empty_folder_is_used(tmp_path) -> None:
    (tmp_path / "t").mkdir()
    assert tree.write(_load(EXAMPLES / "sales_schema.export.json"), tmp_path / "t") > 1
    assert tree.is_tree(tmp_path / "t")


def test_the_command_refuses_a_folder_it_would_not_replace(tmp_path, capsys) -> None:
    (tmp_path / "file.txt").write_text("x")
    assert export_main([str(EXAMPLE), "sales_schema", "--tree", str(tmp_path / "file.txt")]) == 2
    assert "not a Schema tree" in capsys.readouterr().err


def test_output_and_tree_cannot_both_be_given(tmp_path) -> None:
    with pytest.raises(SystemExit):
        export_main([str(EXAMPLE), "sales_schema", "-o", str(tmp_path / "x"), "--tree", str(tmp_path / "t")])


def test_a_tree_from_something_else_is_refused() -> None:
    with pytest.raises(tree.TreeError):
        tree.assemble(lambda path: {"format": "something-else"})
