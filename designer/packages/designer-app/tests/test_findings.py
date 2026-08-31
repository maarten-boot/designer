"""The model check, arranged for reading.

Headless: the ordering, the wording and where a finding points are decidable
without a display, and a list you have to read on screen to check is a list
nobody checks.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import Session
from designer_model.stdlib import standard_library

from designer_app import findings

EXAMPLE = pathlib.Path(__file__).resolve().parents[3] / "examples" / "sales.json"


@pytest.fixture
def session():
    return Session.open(EXAMPLE)


@pytest.fixture
def library():
    return standard_library()


def rows_for(session, library):
    return findings.summarise(session.model, session.full_check(), library)


# --- what the list holds -----------------------------------------------------


def test_every_finding_appears(session, library) -> None:
    report = session.full_check()
    assert len(findings.summarise(session.model, report, library)) == len(report.findings)


def test_the_worst_reads_first(session, library) -> None:
    order = [row.severity for row in rows_for(session, library)]
    assert order == sorted(order, key=findings.ORDER.index)


def test_each_row_names_the_item_and_the_field(session, library) -> None:
    """ "1 warning" tells you nothing; this has to say which, about what."""
    row = next(r for r in rows_for(session, library) if r.code == "MOD101")
    assert row.where == "Type Weight · parent"


def test_each_row_carries_the_message_in_words(session, library) -> None:
    row = next(r for r in rows_for(session, library) if r.code == "MOD101")
    assert "has no parent yet" in row.message
    assert "{" not in row.message, "an argument was never substituted"


def test_a_row_knows_what_it_points_at(session, library) -> None:
    """Double-clicking has to reach the item, so the row carries its identity."""
    weight = next(t for t in session.model.types if t.name == "Weight")
    row = next(r for r in rows_for(session, library) if r.code == "MOD101")
    assert row.item == weight.uuid
    assert row.kind == "Type"


def test_a_row_says_whether_it_stops_an_export(session, library) -> None:
    rows = {r.code: r for r in rows_for(session, library)}
    assert rows["MOD101"].blocks_export
    assert not rows["MOD601"].blocks_export


def test_the_severity_is_spelled_out(session, library) -> None:
    """`incomplete` reads as a fault; unfinished is what it means."""
    markers = {row.marker for row in rows_for(session, library)}
    assert "unfinished" in markers
    assert markers <= set(findings.MARKERS.values())


def test_a_built_in_is_named_not_numbered(session, library) -> None:
    row = next(r for r in rows_for(session, library) if r.code == "MOD602")
    assert "in_past" in row.message


# --- the headline ------------------------------------------------------------


def test_the_headline_names_the_counts(session) -> None:
    assert findings.headline(session.full_check(), "everything").startswith("1 warning, 1 unfinished, 1 note")


def test_the_headline_says_what_would_block_an_export(session) -> None:
    """A total hides whether any of them stops the thing you are building."""
    assert "would block an export" in findings.headline(session.full_check())


def test_a_clean_model_says_so(session) -> None:
    weight = next(t for t in session.model.types if t.name == "Weight")
    session.model.types.remove(weight)
    auditable = next(e for e in session.model.entities if e.name == "Auditable")
    auditable.validators.clear()
    assert findings.headline(session.full_check()) == "no findings"


def test_ids_are_stable_across_runs(session, library) -> None:
    """The window replaces its rows as the model changes; unstable ids would
    lose the selection every time."""
    first = [row.id for row in rows_for(session, library)]
    second = [row.id for row in rows_for(session, library)]
    assert first == second


# --- how much to show --------------------------------------------------------


def test_warnings_and_above_by_default(session, library) -> None:
    """A model under construction is full of unfinished items and unreferenced
    types; a list that is mostly noise trains people to ignore it."""
    assert findings.DEFAULT_LEVEL == "warning"
    shown = findings.at_least(rows_for(session, library), findings.DEFAULT_LEVEL)
    assert {row.code for row in shown} == {"MOD602"}


def test_each_level_shows_that_severity_and_worse(session, library) -> None:
    rows = rows_for(session, library)
    counts = {level: len(findings.at_least(rows, level)) for level in findings.LEVELS}
    assert counts["error"] <= counts["warning"] <= counts["unfinished"] <= counts["everything"]
    assert counts["everything"] == len(rows)


def test_the_noisy_ones_are_what_gets_hidden(session, library) -> None:
    """ "referenced by nothing" for every half-built type is the noise."""
    hidden = {
        row.code
        for row in rows_for(session, library)
        if row not in findings.at_least(rows_for(session, library), "warning")
    }
    assert "MOD601" in hidden  # orphan
    assert "MOD101" in hidden  # unfinished


def test_the_headline_counts_what_it_hid(session) -> None:
    assert "2 hidden" in findings.headline(session.full_check(), "warning")


def test_an_export_blocker_is_named_at_every_level(session) -> None:
    """Hiding those would let a model reach an export with a fault nobody was
    shown — the incomplete items that block it are exactly what a low level
    filters out."""
    for level in findings.LEVELS:
        assert "would block an export" in findings.headline(session.full_check(), level)


def test_a_level_that_hides_everything_still_says_so(session) -> None:
    headline = findings.headline(session.full_check(), "error")
    assert "nothing at this level" in headline
    assert "3 hidden" in headline


def test_an_unknown_level_shows_everything(session, library) -> None:
    """A settings file from a newer build must not blank the list."""
    rows = rows_for(session, library)
    assert findings.at_least(rows, "nonsense") == rows


def test_two_findings_on_look_alike_items_get_different_ids(session, library) -> None:
    """`str(subject)` shortens a uuid to eight characters, and every entity in
    a hand-numbered model begins `e0000000`. Building the row id from the
    display string collapsed distinct findings into one, and the window then
    refused to open at all."""
    import datetime as dt
    from uuid import uuid4

    from designer_model.model import Entity

    model = session.model
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    base = next(e for e in model.entities if e.name == "Auditable")
    base.identity = (base.slots[0].uuid,)
    for name in ("Alpha", "Beta"):
        child = Entity(
            uuid=uuid4(),
            name=name,
            description="",
            created=now,
            modified=now,
            context=base.context,
            extends=base.uuid,
            identity=(base.slots[0].uuid,),
        )
        model.entities.append(child)

    report = session.full_check()
    rows = findings.summarise(model, report, library)
    assert len({str(f.subject) for f in report.findings}) < len(report.findings), (
        "the display strings should collide, or this is not testing anything"
    )
    assert len({row.id for row in rows}) == len(rows)


def test_a_row_id_survives_the_same_code_twice_on_one_item(session, library) -> None:
    rows = findings.summarise(session.model, session.full_check(), library)
    assert len({row.id for row in rows}) == len(rows)
