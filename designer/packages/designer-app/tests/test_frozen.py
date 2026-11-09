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


WORKFLOWS = pathlib.Path(__file__).resolve().parents[4] / ".github" / "workflows"
FREEZE_REQUIREMENTS = pathlib.Path(__file__).resolve().parents[3] / "tools" / "freeze-requirements.txt"


def test_every_action_is_pinned_by_hash_and_every_image_by_digest() -> None:
    """Pinning.md: a tag can be moved to other code, a hash cannot. Runners
    cannot be pinned, but are named by version, never `-latest`."""
    import re

    found = sorted(WORKFLOWS.glob("*.yml"))
    assert found
    for workflow in found:
        text = workflow.read_text(encoding="utf-8")
        for line in re.findall(r"uses:\s*(\S+.*)", text):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+(\.\d+)*", line), (workflow.name, line)
        for image in re.findall(r"image:\s*(\S+)", text):
            assert re.fullmatch(r"[\w.-]+:[\w.-]+@sha256:[0-9a-f]{64}", image), (workflow.name, image)
        assert "-latest" not in text, workflow.name


def test_freezing_installs_pyinstaller_by_hash() -> None:
    lines = FREEZE_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    pins = [line for line in lines if line and not line.startswith(("#", " "))]
    assert any(p.startswith("pyinstaller==") for p in pins)
    for pin in pins:
        assert "==" in pin and pin.endswith("\\"), pin  # one version, then its hashes
    assert "--require-hashes" in (WORKFLOWS / "frozen.yml").read_text(encoding="utf-8")
    freeze = (FREEZE_REQUIREMENTS.parent / "freeze.py").read_text(encoding="utf-8")
    assert '"--require-hashes"' in freeze and "freeze-requirements.txt" in freeze


def test_freezing_writes_nothing_into_the_repository() -> None:
    """FRZ-6, the NFS-share rule: PyInstaller works in a temporary folder, its
    environment lives in the machine's cache, and the one output folder is
    ignored by git."""
    root = FREEZE_REQUIREMENTS.parents[1]
    freeze = (root / "tools" / "freeze.py").read_text(encoding="utf-8")
    assert 'tempfile.mkdtemp(prefix="designer-freeze-")' in freeze
    assert "environment = CACHE /" in freeze
    assert "dist-frozen/" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
