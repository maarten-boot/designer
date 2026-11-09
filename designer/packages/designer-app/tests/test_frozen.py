"""The frozen build's entry point: what each flag starts (spec §14.5)."""

from __future__ import annotations

import io
import json
import pathlib
import sys

from designer_model import bench, dump, load

from designer_app import frozen

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


def test_the_worker_flag_runs_the_bench_worker(monkeypatch, capsys) -> None:
    model = load(EXAMPLE)
    request = {"model": dump(model), "type": str(model.types[0].uuid), "text": "x"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    assert frozen.main([bench.WORKER_FLAG]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["text"] == "x" and not answer.get("stopped")


def test_no_flag_starts_the_application(monkeypatch) -> None:
    seen: list[list[str]] = []

    def application(args: list[str]) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr("designer_app.main.main", application)
    assert frozen.main(["model.json"]) == 0
    assert seen == [["model.json"]]


def test_a_self_test_needs_a_model_and_a_report(capsys) -> None:
    assert frozen.main([frozen.SELF_TEST, "only-one"]) == 2
    assert "usage" in capsys.readouterr().err


def test_a_failed_self_test_says_why_in_its_report(tmp_path) -> None:
    report = tmp_path / "report.txt"
    assert frozen.self_test(str(tmp_path / "missing.json"), str(report)) == 1
    assert "missing.json" in report.read_text()
