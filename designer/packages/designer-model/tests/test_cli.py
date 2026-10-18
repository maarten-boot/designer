"""designer-check and designer-export, as an installed user runs them."""

from __future__ import annotations

import json
import pathlib

from designer_model.cli import check_main, export_main

EXAMPLES = pathlib.Path(__file__).resolve().parents[3] / "examples"
EXAMPLE = EXAMPLES / "sales.json"


def test_check_passes_the_worked_example(capsys) -> None:
    assert check_main([str(EXAMPLE), "--level", "everything"]) == 0
    out = capsys.readouterr().out
    assert "round trip: unchanged" in out
    for code in ("MOD602", "MOD101", "MOD601"):
        assert code in out


def test_check_speaks_json(capsys) -> None:
    assert check_main([str(EXAMPLE), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["round_trip"] is True
    assert sorted(f["code"] for f in report["findings"]) == ["MOD101", "MOD601", "MOD602"]


def test_a_file_that_cannot_be_loaded_is_a_message_not_a_traceback(tmp_path, capsys) -> None:
    broken = tmp_path / "broken.json"
    text = EXAMPLE.read_text().replace('"decimal": "0.00"', '"decimal": 0.0', 1)
    broken.write_text(text)
    assert check_main([str(broken)]) == 2
    assert "decimal is written as a string" in capsys.readouterr().err


def test_export_reproduces_the_committed_file(capsys) -> None:
    assert export_main([str(EXAMPLE), "sales_schema"]) == 0
    assert capsys.readouterr().out == (EXAMPLES / "sales_schema.export.json").read_text()


def test_export_to_a_file(tmp_path) -> None:
    target = tmp_path / "out.json"
    assert export_main([str(EXAMPLE), "support_schema", "-o", str(target)]) == 0
    assert target.read_text() == (EXAMPLES / "support_schema.export.json").read_text()


def test_an_unknown_schema_lists_the_ones_there_are(capsys) -> None:
    assert export_main([str(EXAMPLE), "nope"]) == 2
    assert "there are: sales_schema, support_schema" in capsys.readouterr().err


def test_a_blocked_export_lists_its_blockers(tmp_path, capsys) -> None:
    document = json.loads(EXAMPLE.read_text())
    schema = next(s for s in document["schemas"] if s["name"] == "sales_schema")
    schema["members"] = [m for m in schema["members"] if m != "e0000000-0000-4000-8000-000000000002"]
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps(document))
    assert export_main([str(blocked), "sales_schema"]) == 1
    assert "MOD503" in capsys.readouterr().err
